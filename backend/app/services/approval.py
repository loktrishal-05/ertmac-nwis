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
from app.db.models import ActionRevision, ApprovalDecision, EvidenceManifest, EvidenceManifestItem, GovernanceRequest, User
from app.services.audit import append_event
from app.services.evidence_integrity import get_evidence_integrity_status
from app.services.governance import POLICY_VERSION as REVISION_POLICY_VERSION
from app.services.governance import (ReleaseNotAllowed, _ledger_state, _without_authority, assert_release_allowed,
                                     assert_still_approved_under_lock)

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
    # Phase 5D: read-only summary only -- evidence_type/evidence_id/
    # source_identifier/hashes, never the raw content the item's hash covers
    # (docs/phase5d.md, "APIs": "do not expose unnecessary raw sensitive data").
    manifest = session.execute(
        select(EvidenceManifest).where(EvidenceManifest.action_revision_id == revision_id)
    ).scalar_one_or_none()
    item_summaries = []
    if manifest is not None:
        items = session.scalars(
            select(EvidenceManifestItem).where(EvidenceManifestItem.manifest_id == manifest.id)
            .order_by(EvidenceManifestItem.item_index)
        ).all()
        item_summaries = [
            {"item_index": item.item_index, "evidence_type": item.evidence_type, "evidence_id": item.evidence_id,
             "source_identifier": item.source_identifier, "canonical_item_hash": item.canonical_item_hash}
            for item in items
        ]
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
        "evidence_binding_status": get_evidence_integrity_status(session, revision_id),
        "evidence_manifest_id": manifest.id if manifest else None,
        "evidence_manifest_hash": manifest.canonical_manifest_hash if manifest else None,
        "evidence_item_summaries": item_summaries,
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
    # entirely). Phase 5F H1: `session.get(User, id)` is NOT a fresh read --
    # if a `User` with this id is already attached to `session`'s identity
    # map (the caller's own object, or one loaded earlier in this same
    # session), SQLAlchemy returns that SAME cached Python object without
    # re-querying the database, so a caller-mutated `.role` (or a role that
    # was demoted in the database by someone else after that object was
    # loaded) is silently trusted. A plain column-only SELECT is never
    # served from the identity map -- it always issues a real query and
    # returns a bare scalar, never an ORM instance -- so this is a genuine
    # fresh read of the CURRENT database value every single call.
    # `no_autoflush` additionally guarantees that a caller's dirty, mutated
    # `User.role` attribute is never flushed to the database as a side
    # effect of merely checking authorization here.
    reviewer_id = getattr(reviewer, "id", None)
    with session.no_autoflush:
        authoritative_role = session.execute(
            select(User.role).where(User.id == reviewer_id)
        ).scalar_one_or_none()
    if reviewer_id is None or authoritative_role not in ("reviewer", "admin"):
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
            if existing.approver_id == reviewer_id and existing.decision == decision_upper:
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
        if binding.requester_user_id == reviewer_id:
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
            "approver_id": reviewer_id, "decision": "REVOKE", "decided_at": now,
            "approval_purpose": revision.approval_purpose, "policy_version": APPROVAL_POLICY_VERSION,
            "reviewer_comment": reviewer_comment, "expires_at": None,
            "revoked_decision_id": approve_row.id, "revoked_at": now, "revoked_by": reviewer_id,
        }
    else:
        expires_at = now + timedelta(seconds=settings.approval_validity_seconds) if decision_upper == "APPROVE" else None
        values = {
            "request_id": revision.request_id, "action_id": revision.action_id, "action_revision_id": revision_id,
            "canonical_request_hash": revision.canonical_request_hash,
            "canonical_proposal_hash": revision.canonical_proposal_hash,
            "approver_id": reviewer_id, "decision": decision_upper, "decided_at": now,
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

    if winner.approver_id != reviewer_id or winner.decision != decision_upper:
        raise DecisionConflict(
            f"This revision was already decided ({winner.decision} by a different reviewer at "
            f"{winner.decided_at.isoformat()}); this decision was not recorded"
        )

    # Mandatory, same-transaction (Phase 5C, docs/phase5c.md "Atomic
    # governance/audit behavior"): only reached once `winner` is confirmed to
    # be OUR OWN freshly-inserted decision (never on a losing race, and never
    # on an idempotent same-reviewer/same-decision retry that returned early
    # above) -- exactly once per actual authoritative decision. If the audit
    # append fails, the exception propagates and the caller's transaction
    # rolls back the decision too, rather than leaving it unaudited.
    event_type = {"APPROVE": "APPROVAL_DECISION_APPROVE", "REJECT": "APPROVAL_DECISION_REJECT",
                 "REVOKE": "APPROVAL_DECISION_REVOKE"}[decision_upper]
    append_event(
        session, event_type=event_type, actor_id=reviewer_id, actor_kind="user",
        request_id=revision.request_id, action_revision_id=revision.id, decision_id=winner.id,
        payload={"decision": decision_upper, "requester_user_id": binding.requester_user_id,
                "policy_version": winner.policy_version},
    )
    return winner


def release_advisory(session, revision_id: UUID, *, actor: User) -> dict:
    """The shared release gate (docs/phase5b.md section 10): hands back an
    already-APPROVED advisory recommendation for human/operational
    consideration. This is never execution and creates no new capability --
    assert_release_allowed fails closed for anything but APPROVED.

    Phase 5C: release success is a mandatory, fail-closed audit event
    (docs/phase5c.md "Atomic governance/audit behavior") -- this function
    commits its own transaction (release itself makes no OTHER write) only
    after the audit append succeeds; if it fails, the exception propagates
    and no release is reported to have happened."""
    assert_release_allowed(session, revision_id)
    # Phase 5F H2: assert_release_allowed's own validation (including the
    # evidence-integrity check) holds no lock and takes real time; a
    # concurrent revoke could commit strictly between it finishing and this
    # function's own commit below. This re-verifies APPROVED one last time
    # under a row lock held through the rest of this function, so a
    # concurrent decision on this exact revision can now only land strictly
    # before this check or strictly after this function's commit -- never
    # silently in between (docs/phase5f-validation.md H2).
    assert_still_approved_under_lock(session, revision_id)
    detail = revision_detail(session, revision_id)
    detail["governance_status"] = "RELEASED"
    detail["released_at"] = datetime.now(timezone.utc)
    append_event(
        session, event_type="ADVISORY_RELEASE_SUCCESS", actor_id=actor.id, actor_kind="user",
        request_id=detail["request_id"], action_revision_id=revision_id,
        payload={"route": detail.get("route")},
    )
    session.commit()
    return detail
