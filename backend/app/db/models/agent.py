"""Agent persistence model."""

from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin, CreatedAtMixin


class Agent(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(100), unique=True)
    agent_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="not_started", server_default="not_started")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

