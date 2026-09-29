"""Phase 5C tamper-evident audit chain response contracts. The legacy Phase 2
AuditLogResponse (app.db.models.AuditLog) is retired here: that table has
never had a row written to it (see docs/phase5c.md, "Legacy audit data") and
nothing else in the codebase references it."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    chain_id: str
    sequence_number: int
    occurred_at: datetime
    actor_id: UUID | None
    actor_kind: str
    event_type: str
    request_id: UUID | None
    action_revision_id: UUID | None
    decision_id: UUID | None
    payload: dict
    canonical_payload_hash: str
    payload_redacted: bool = True
    previous_hash: str
    event_hash: str


class AuditVerifyResponse(BaseModel):
    valid: bool
    chain_id: str
    events_checked: int
    first_sequence: int | None
    last_sequence: int | None
    head_hash: str | None
    first_error_sequence: int | None
    error_type: str | None
