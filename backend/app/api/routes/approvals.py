"""Phase 5B authenticated human approval workflow.

GET /approvals and POST /approvals/{id} are the legacy Phase 2 placeholder
route (POST kept byte-for-byte; GET is repurposed below -- see
docs/phase5b.md, "legacy Approval handling"). Everything else here is real:
authenticated reviewers only, exact-revision/hash re-verification on every
decision, and a fail-closed release gate.
"""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.models import GovernanceRequest, User
from app.db.session import get_db
from app.schemas.approval import (
    ApprovalPlaceholder,
    DecisionRequest,
    DecisionResult,
    PendingRevisionSummary,
    ReleaseResult,
    RevisionDetail,
)
from app.services.approval import DecisionConflict, DecisionNotAllowed, apply_decision, pending_reviews, release_advisory, revision_detail
from app.services.audit import append_event
from app.services.governance import ReleaseNotAllowed

router = APIRouter(tags=["approvals"])


@router.post("/approvals/{approval_id}", response_model=ApprovalPlaceholder)
def review_approval(approval_id: UUID) -> ApprovalPlaceholder:
    return ApprovalPlaceholder()


@router.get("/approvals", response_model=list[PendingRevisionSummary])
def list_pending_approvals(user: User = Depends(require_role("reviewer", "admin")),
                           session: Session = Depends(get_db)) -> list[PendingRevisionSummary]:
    revisions = pending_reviews(session, viewer=user)
    summaries = []
    for rev in revisions:
        route = json.loads(rev.canonical_proposal)["payload"].get("route")
        binding = session.get(GovernanceRequest, rev.request_id)
        summaries.append(PendingRevisionSummary(
            action_revision_id=rev.id, request_id=rev.request_id, route=route,
            created_at=rev.created_at, requester_user_id=binding.requester_user_id if binding else None,
        ))
    return summaries


@router.get("/approvals/{revision_id}", response_model=RevisionDetail)
def get_approval(revision_id: UUID, user: User = Depends(require_role("reviewer", "admin")),
                 session: Session = Depends(get_db)) -> RevisionDetail:
    try:
        return RevisionDetail(**revision_detail(session, revision_id))
    except DecisionNotAllowed as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/approvals/{revision_id}/decision", response_model=DecisionResult)
def decide_approval(revision_id: UUID, payload: DecisionRequest,
                    user: User = Depends(require_role("reviewer", "admin")),
                    session: Session = Depends(get_db)) -> DecisionResult:
    try:
        decision = apply_decision(
            session, revision_id=revision_id, reviewer=user, decision=payload.decision,
            reviewer_comment=payload.reviewer_comment, expected_revision_id=payload.expected_revision_id,
        )
        session.commit()
    except DecisionNotAllowed as error:
        session.rollback()
        # Best-effort (docs/phase5c.md "Atomic governance/audit behavior"):
        # nothing authoritative changed, so a failure to record this denial
        # must never turn a correct 403/404 into a 500. The session was just
        # rolled back to a clean state, so this starts and commits its own
        # small, independent transaction.
        try:
            append_event(session, event_type="APPROVAL_AUTHORIZATION_DENIED", actor_id=user.id, actor_kind="user",
                        action_revision_id=revision_id, payload={"attempted_decision": payload.decision, "reason": str(error)})
            session.commit()
        except Exception:
            session.rollback()
        raise HTTPException(status_code=403 if "identity is unverified" in str(error)
                            or "Self-approval" in str(error)
                            or "authorized reviewer" in str(error) else 404, detail=str(error)) from error
    except DecisionConflict as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    return DecisionResult(
        decision_id=decision.id, action_revision_id=decision.action_revision_id, decision=decision.decision,
        governance_status={"APPROVE": "APPROVED", "REJECT": "REJECTED", "REVOKE": "REVOKED"}[decision.decision],
        decided_at=decision.decided_at,
    )


@router.get("/approvals/{revision_id}/release", response_model=ReleaseResult)
def release_approval(revision_id: UUID, user: User = Depends(get_current_user),
                     session: Session = Depends(get_db)) -> ReleaseResult:
    try:
        return ReleaseResult(**release_advisory(session, revision_id, actor=user))
    except ReleaseNotAllowed as error:
        session.rollback()
        # Best-effort, same reasoning as the decision-denial case above:
        # nothing state-changing happened, so this must never turn a correct
        # 403 into a 500.
        try:
            append_event(session, event_type="ADVISORY_RELEASE_DENIED", actor_id=user.id, actor_kind="user",
                        action_revision_id=revision_id, payload={"reason": str(error)})
            session.commit()
        except Exception:
            session.rollback()
        raise HTTPException(status_code=403, detail=str(error)) from error
