"""AuditLog persistence model."""

import uuid
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin, CreatedAtMixin


class AuditLog(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_logs"

    event_type: Mapped[str] = mapped_column(String(100), index=True)
    actor: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[uuid.UUID | None]
    event_data: Mapped[dict | None] = mapped_column(JSONB)
    previous_hash: Mapped[str | None] = mapped_column(String(128))
    current_hash: Mapped[str | None] = mapped_column(String(128))

