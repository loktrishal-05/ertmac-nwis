"""Phase 5C tamper-evident audit chain API. Read-only: no route here accepts
an event_hash, previous_hash, sequence_number, or any other authority-shaped
field from a client -- every AuditEvent row is written exclusively by
app.services.audit.append_event, called only from server-side governance/
approval/auth code (see docs/phase5c.md, "API changes"). Role-gated the same
way as the Phase 5B approvals list (reviewer/admin only) since audit content
can reveal governance/approval activity beyond what a plain requester sees."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.models import AuditEvent, User
from app.db.session import get_db
from app.schemas.audit import AuditEventResponse, AuditVerifyResponse
from app.services.audit import CHAIN_ID, verify_chain

router = APIRouter(tags=["audit"])

_MAX_LOG_LIMIT = 500


@router.get("/audit/log", response_model=list[AuditEventResponse])
def audit_log(limit: int = 100, user: User = Depends(require_role("reviewer", "admin")),
              session: Session = Depends(get_db)) -> list[AuditEventResponse]:
    limit = max(1, min(limit, _MAX_LOG_LIMIT))
    events = session.scalars(
        select(AuditEvent).where(AuditEvent.chain_id == CHAIN_ID)
        .order_by(AuditEvent.sequence_number.desc()).limit(limit)
    ).all()
    return [AuditEventResponse.model_validate(event) for event in events]


@router.get("/audit/verify", response_model=AuditVerifyResponse)
def audit_verify(user: User = Depends(require_role("reviewer", "admin")),
                 session: Session = Depends(get_db)) -> AuditVerifyResponse:
    return AuditVerifyResponse(**verify_chain(session))
