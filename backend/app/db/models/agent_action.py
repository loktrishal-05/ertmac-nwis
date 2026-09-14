"""AgentAction persistence model."""

import uuid
from sqlalchemy import String, Text, Float, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin, CreatedAtMixin


class AgentAction(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "agent_actions"

    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(100))
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50), default="not_started", server_default="not_started")
    __table_args__ = (CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),)

