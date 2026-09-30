"""Phase 5C tamper-evident audit chain API. Read-only: no route here accepts
an event_hash, previous_hash, sequence_number, or any other authority-shaped
field from a client -- every AuditEvent row is written exclusively by
app.services.audit.append_event, called only from server-side governance/
approval/auth code (see docs/phase5c.md, "API changes"). Role-gated the same
way as the Phase 5B approvals list (reviewer/admin only) since audit content
can reveal governance/approval activity beyond what a plain requester sees."""
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response
from app.services import ui_reads
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.models import AuditEvent, User, VerifiedKnowledge
from app.db.session import get_db
from app.schemas.audit import AuditEventResponse, AuditVerifyResponse
from app.services.audit import CHAIN_ID, verify_chain

router = APIRouter(tags=["audit"])

@router.get("/audit/log", response_model=list[AuditEventResponse])
def audit_log(response: Response, limit: int = Query(100, ge=1, le=500),
              before_sequence: int | None = Query(None, ge=1),
              start: datetime | None = None, end: datetime | None = None,
              event_type: str | None = Query(None, max_length=60),
              user_id: UUID | None = None, execution_id: UUID | None = None,
              approval_id: UUID | None = None, knowledge_id: UUID | None = None,
              user: User = Depends(require_role("reviewer", "admin")),
              session: Session = Depends(get_db)) -> list[AuditEventResponse]:
    start, end = ui_reads.validate_range(start, end)
    query = select(AuditEvent).where(AuditEvent.chain_id == CHAIN_ID)
    for column, value in ((AuditEvent.event_type, event_type), (AuditEvent.actor_id, user_id),
                          (AuditEvent.action_revision_id, approval_id)):
        if value is not None:
            query = query.where(column == value)
    if execution_id:
        query = query.where(or_(AuditEvent.request_id == execution_id,
            AuditEvent.payload["run_id"].as_string() == str(execution_id)))
    if knowledge_id:
        query = query.where(AuditEvent.action_revision_id.in_(select(VerifiedKnowledge.approval_revision_id)
                            .where(VerifiedKnowledge.id == knowledge_id, VerifiedKnowledge.access_scope == "internal")))
    if start:
        query = query.where(AuditEvent.occurred_at >= start)
    if end:
        query = query.where(AuditEvent.occurred_at < end)
    if before_sequence:
        query = query.where(AuditEvent.sequence_number < before_sequence)
    events = session.scalars(query.order_by(AuditEvent.sequence_number.desc()).limit(limit + 1)).all()
    response.headers["X-Has-More"] = str(len(events) > limit).lower()
    response.headers["X-Sample-Size"] = str(min(len(events), limit))
    response.headers["X-As-Of"] = ui_reads.now().isoformat()
    # Keep hashes and linkage; raw payload remains on the server for /audit/verify.
    return [AuditEventResponse.model_validate(event).model_copy(update={"payload": {}})
            for event in events[:limit]]


@router.get("/audit/verify", response_model=AuditVerifyResponse)
def audit_verify(user: User = Depends(require_role("reviewer", "admin")),
                 session: Session = Depends(get_db)) -> AuditVerifyResponse:
    return AuditVerifyResponse(**verify_chain(session))
