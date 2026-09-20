"""Phase 5B approval-decision boundary: approve/reject/revoke the EXACT
immutable revision a reviewer inspected, and the advisory release gate.

Approval never grants SCADA/DCS/plant-write/permit/LOTO/isolation authority --
it only lets an already-generated advisory recommendation be handed back for
human/operational consideration. See app.services.governance.assert_release_allowed
for the release gate itself; this module only decides APPROVE/REJECT/REVOKE.
"""
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.config import settings
from app.db.models import ActionRevision, ApprovalDecision, GovernanceRequest, User
from app.services.governance import POLICY_VERSION as REVISION_POLICY_VERSION
from app.services.governance import ReleaseNotAllowed, _ledger_state, _without_authority, assert_release_allowed

APPROVAL_POLICY_VERSION = "governance-5b-v1"


class DecisionConflict(ValueError):
    """A different terminal decision already exists for this revision."""


class DecisionNotAllowed(PermissionError):
    """The caller/revision/state does not permit this decision. Fail closed."""


def _insert_decision_once(session, values: dict) -> None:
    dialect = session.get_bind().dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise ValueError("Unsupported governance database")
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    session.execute(insert(ApprovalDecision).values(**values).on_conflict_do_nothing())


def _load_binding_and_revision(session, revision_id: UUID):
    # with_for_update serializes concurrent decisions on the SAME revision,
    # the same technique Phase 5A uses to lock a GovernanceRequest row.
    revision = session.scalars(
        select(ActionRevision).where(ActionRevision.id == revision_id).with_for_update()
    ).one_or_none()
    if revision is None:
        raise DecisionNotAllowed("No recognized governed revision")
    binding = session.get(GovernanceRequest, revision.request_id)
    if binding is None:
        raise DecisionNotAllowed("Revision has no governing request binding")
    return binding, revision


def pending_reviews(session, *, viewer: User) -> list[ActionRevision]:
    """Revisions currently PENDING_REVIEW that `viewer` did not themselves
    request. (Whether they may actually decide one -- e.g. an unverified
    requester -- is re-checked, authoritatively, inside apply_decision.)"""
    candidates = session.scalars(
        select(ActionRevision).join(GovernanceRequest, GovernanceRequest.id == ActionRevision.request_id)
        .where(ActionRevision.governance_status == "PENDING_REVIEW",
              (GovernanceRequest.requester_user_id.is_(None)) | (GovernanceRequest.requester_user_id != viewer.id))
        .order_by(ActionRevision.created_at)
    ).all()
    return [rev for rev in candidates if (_ledger_state(session, rev.id) or "PENDING_REVIEW") == "PENDING_REVIEW"]


def revision_detail(session, revision_id: UUID) -> dict:
    revision = session.get(ActionRevision, revision_id)
    if revision is None:
        raise DecisionNotAllowed("No recognized governed revision")
    binding = session.get(GovernanceRequest, revision.request_id)
    proposal = json.loads(revision.canonical_proposal)["payload"]
    decisions = session.scalars(
        select(ApprovalDecision).where(ApprovalDecision.action_revision_id == revision_id)
        .order_by(ApprovalDecision.decided_at)
    ).all()
    return {
        "action_revision_id": revision.id,
        "request_id": revision.request_id,
        "action_id": revision.action_id,
        "governance_status": _ledger_state(session, revision_id) or "PENDING_REVIEW",
        "route": proposal.get("route"),
        "agent_result": _without_authority(proposal.get("agent_result")),
        "evidence": proposal.get("evidence", []),
        "warnings": proposal.get("warnings", []),
        "canonical_request_hash": revision.canonical_request_hash,
        "canonical_proposal_hash": revision.canonical_proposal_hash,
        "evidence_binding_status": revision.evidence_binding_status,
        "policy_version": revision.policy_version,
        "requester_user_id": binding.requester_user_id if binding else None,
        "decisions": [
            {
                "decision_id": row.id, "approver_id": row.approver_id, "decision": row.decision,
                "decided_at": row.decided_at, "reviewer_comment": row.reviewer_comment,
                "expires_at": row.expires_at, "revoked_decision_id": row.revoked_decision_id,
            }
            for row in decisions
        ],
    }


def apply_decision(session, *, revision_id: UUID, reviewer: User, decision: str,
                   reviewer_comment: str | None = None, expected_revision_id: UUID | None = None) -> ApprovalDecision:
    """decision is one of "approve" | "reject" | "revoke" (schema-validated).

    Every check reloads fresh backend state; nothing here ever trusts a
    caller-supplied hash, approver id, role, or revision beyond the path
    parameter re-verified against the database. Any mismatch fails closed.
    """
    decision_upper = decision.upper()
    if decision_upper not in ("APPROVE", "REJECT", "REVOKE"):
        raise ValueError(f"Unknown decision {decision!r}")

    # Authorization is enforced HERE, at the service boundary -- never only by
    # the HTTP layer's require_role dependency. A caller-supplied `reviewer`
    # object's .id/.role are never trusted as-is (an in-memory object can be
    # freely mutated, or belong to a caller who skipped the API layer
    # entirely); the service reloads the authoritative row by id and re-checks
    # its role fresh from the database before anything else happens.
    reviewer = session.get(User, getattr(reviewer, "id", None))
    if reviewer is None or reviewer.role not in ("reviewer", "admin"):
        raise DecisionNotAllowed("Only an authorized reviewer or admin may decide a governed revision")

    if expected_revision_id is not None and expected_revision_id != revision_id:
        raise DecisionConflict("expected_revision_id does not match the revision being decided")

    binding, revision = _load_binding_and_revision(session, revision_id)

    if revision.approval_purpose != "ADVISORY_DRAFT_REVIEW":
        raise DecisionNotAllowed("Unrecognized approval purpose")
    if revision.policy_version != REVISION_POLICY_VERSION:
        raise DecisionNotAllowed("Unrecognized policy version")

    current_state = _ledger_state(session, revision_id) or "PENDING_REVIEW"

    if decision_upper in ("APPROVE", "REJECT"):
        if current_state != "PENDING_REVIEW":
            # A same-reviewer, same-decision retry is not a conflict -- it is
            # exactly the idempotent-retry contract this service promises.
            existing = session.execute(
                select(ApprovalDecision).where(ApprovalDecision.action_revision_id == revision_id,
                                               ApprovalDecision.decision.in_(("APPROVE", "REJECT")))
            ).scalar_one()
            if existing.approver_id == reviewer.id and existing.decision == decision_upper:
                return existing
            raise DecisionConflict(f"Revision already has a terminal decision (currently {current_state})")
        if binding.requester_user_id is None:
            # Fail closed (docs/phase5b.md, self-approval policy): a revision
            # created by an unauthenticated /query call has no verified
            # requester, so self-approval cannot be ruled out. There is no
            # convenience bypass -- resubmit the query as an authenticated
            # requester to make it reviewable.
            raise DecisionNotAllowed(
                "This revision's requester identity is unverified (created by an unauthenticated "
                "/query call); it cannot be reviewed until resubmitted by an authenticated requester"
            )
        if binding.requester_user_id == reviewer.id:
            raise DecisionNotAllowed("Self-approval is prohibited: the requester cannot review their own request")
    else:  # REVOKE
        if current_state != "APPROVED":
            raise DecisionNotAllowed(f"Only an APPROVED revision can be revoked (currently {current_state})")

    now = datetime.now(timezone.utc)
    if decision_upper == "REVOKE":
        approve_row = session.execute(
            select(ApprovalDecision).where(ApprovalDecision.action_revision_id == revision_id,
                                           ApprovalDecision.decision == "APPROVE")
        ).scalar_one()
        values = {
            "request_id": revision.request_id, "action_id": revision.action_id, "action_revision_id": revision_id,
            "canonical_request_hash": revision.canonical_request_hash,
            "canonical_proposal_hash": revision.canonical_proposal_hash,
            "approver_id": reviewer.id, "decision": "REVOKE", "decided_at": now,
            "approval_purpose": revision.approval_purpose, "policy_version": APPROVAL_POLICY_VERSION,
            "reviewer_comment": reviewer_comment, "expires_at": None,
            "revoked_decision_id": approve_row.id, "revoked_at": now, "revoked_by": reviewer.id,
        }
    else:
        expires_at = now + timedelta(seconds=settings.approval_validity_seconds) if decision_upper == "APPROVE" else None
        values = {
            "request_id": revision.request_id, "action_id": revision.action_id, "action_revision_id": revision_id,
            "canonical_request_hash": revision.canonical_request_hash,
            "canonical_proposal_hash": revision.canonical_proposal_hash,
            "approver_id": reviewer.id, "decision": decision_upper, "decided_at": now,
            "approval_purpose": revision.approval_purpose, "policy_version": APPROVAL_POLICY_VERSION,
            "reviewer_comment": reviewer_comment, "expires_at": expires_at,
            "revoked_decision_id": None, "revoked_at": None, "revoked_by": None,
        }
    _insert_decision_once(session, values)

    # Re-select the actual winner: our own insert may have lost a race to a
    # concurrent decision (the partial unique index is the authority here).
    filter_clause = (ApprovalDecision.decision == "REVOKE") if decision_upper == "REVOKE" else \
        ApprovalDecision.decision.in_(("APPROVE", "REJECT"))
    winner = session.execute(
        select(ApprovalDecision).where(ApprovalDecision.action_revision_id == revision_id, filter_clause)
    ).scalar_one()

    if winner.approver_id != reviewer.id or winner.decision != decision_upper:
        raise DecisionConflict(
            f"This revision was already decided ({winner.decision} by a different reviewer at "
            f"{winner.decided_at.isoformat()}); this decision was not recorded"
        )
    return winner


def release_advisory(session, revision_id: UUID) -> dict:
    """The shared release gate (docs/phase5b.md section 10): hands back an
    already-APPROVED advisory recommendation for human/operational
    consideration. This is never execution and creates no new capability --
    assert_release_allowed fails closed for anything but APPROVED."""
    assert_release_allowed(session, revision_id)
    detail = revision_detail(session, revision_id)
    detail["governance_status"] = "RELEASED"
    detail["released_at"] = datetime.now(timezone.utc)
    return detail
