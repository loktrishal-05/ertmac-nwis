"""Operational recovery state; approval authority remains in the governance ledger."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin
from app.db.models.agent_run import JSONVariant


class DurableExecution(CreatedAtMixin, Base):
    __tablename__ = "durable_executions"
    # request_id = execution_id = thread_id = originating run_id.
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    request: Mapped[dict] = mapped_column(JSONVariant)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    current_node: Mapped[str | None] = mapped_column(String(100))
    retry_class: Mapped[str | None] = mapped_column(String(40))
    resume_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    checkpoint_version: Mapped[int] = mapped_column(Integer, default=0)
    interruption_reason: Mapped[str | None] = mapped_column(String(100))
    resume_reason: Mapped[str | None] = mapped_column(String(100))
    selected_model: Mapped[str] = mapped_column(String(200))
    execution_path: Mapped[str] = mapped_column(String(60))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GraphCheckpoint(Base):
    __tablename__ = "graph_checkpoints"
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("durable_executions.id"), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(200), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(String(100))
    checkpoint: Mapped[dict] = mapped_column(JSONVariant)
    meta: Mapped[dict] = mapped_column(JSONVariant)


class GraphWrite(Base):
    __tablename__ = "graph_writes"
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("durable_executions.id"), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(200), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(200))
    value: Mapped[dict] = mapped_column(JSONVariant)


class ExecutionOperation(Base):
    __tablename__ = "execution_operations"
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("durable_executions.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    status: Mapped[str] = mapped_column(String(30))
    retry_class: Mapped[str | None] = mapped_column(String(40))
    result: Mapped[dict | None] = mapped_column(JSONVariant)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
