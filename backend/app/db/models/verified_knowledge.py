"""Verified statements bind to the existing immutable governance revision."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, IdentityMixin, CreatedAtMixin

class VerifiedKnowledge(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "verified_knowledge"
    __table_args__ = (CheckConstraint("status IN ('CANDIDATE','VERIFIED','STALE','REVOKED')", name="knowledge_status"),)
    title: Mapped[str] = mapped_column(String(200))
    question: Mapped[str] = mapped_column(Text)
    match_key: Mapped[str] = mapped_column(String(64), index=True)
    statement: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    source_snapshot: Mapped[list] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    content_hash: Mapped[str] = mapped_column(String(64))
    access_scope: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="CANDIDATE", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_id: Mapped[UUID | None] = mapped_column(ForeignKey("verified_knowledge.id"))
    approval_revision_id: Mapped[UUID] = mapped_column(ForeignKey("action_revisions.id"), unique=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    verified_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
