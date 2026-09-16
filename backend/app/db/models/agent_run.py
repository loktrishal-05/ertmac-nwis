"""AgentRun persistence model: one row per graph invocation.

Stores the operator's own query text (gated by AGENT_TRACE_STORE_QUERY),
route/status/timings/warnings. Never stores an assembled prompt body,
retrieved document text, OCR quote text, or sensor row values — only
evidence_id references live in the related AgentRunStep rows."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdentityMixin

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class AgentRun(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "agent_runs"

    query_text: Mapped[str | None] = mapped_column(Text)
    route: Mapped[str | None] = mapped_column(String(50), index=True)
    route_confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(200))
    runtime: Mapped[str | None] = mapped_column(String(50))
    gateway_repair_attempts: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list] = mapped_column(JSONVariant, default=list)
