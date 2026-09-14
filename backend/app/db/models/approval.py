"""Approval persistence model."""

import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin, CreatedAtMixin


class Approval(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "approvals"

    action_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_actions.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", server_default="pending")
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewer_comment: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

