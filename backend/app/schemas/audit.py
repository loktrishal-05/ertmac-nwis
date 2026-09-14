"""Audit log response contract."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    event_type: str
    actor: str
    entity_type: str
    entity_id: UUID | None
    event_data: dict | None
    previous_hash: str | None
    current_hash: str | None
    created_at: datetime
