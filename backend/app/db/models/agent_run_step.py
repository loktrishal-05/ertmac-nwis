"""AgentRunStep persistence model: one row per graph node executed.

evidence_ids is an array of evidence_id STRINGS only — never the EvidenceRef
body (quote text, region text, provenance). usage/timings mirror the Phase 4A
GenerationResult shape for nodes that called the model gateway; both are {}
for nodes that did not."""
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class AgentRunStep(IdentityMixin, Base):
    __tablename__ = "agent_run_steps"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    step_index: Mapped[int] = mapped_column(Integer)
    node_name: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    tool_name: Mapped[str | None] = mapped_column(String(100))
    evidence_ids: Mapped[list] = mapped_column(JSONVariant, default=list)
    usage: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    timings: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    warnings: Mapped[list] = mapped_column(JSONVariant, default=list)
    error: Mapped[str | None] = mapped_column(Text)
