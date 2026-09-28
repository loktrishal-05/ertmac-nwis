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
    # Descriptive only: an origin never grants trust; verification stays on the approval ledger.
    origin: Mapped[str] = mapped_column(String(40), default="manual_submission", server_default="manual_submission")
    origin_reference: Mapped[str | None] = mapped_column(String(200))
    asset_scope: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"))


class KnowledgeGap(CreatedAtMixin, Base):
    """Review state for a deterministic gap id; transitions are audited, never model-driven."""
    __tablename__ = "knowledge_gaps"
    __table_args__ = (CheckConstraint("status IN ('OPEN','UNDER_REVIEW','RESOLVED','DISMISSED')", name="gap_status"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    subject: Mapped[str] = mapped_column(String(200))
    gap_type: Mapped[str] = mapped_column(String(80))
    required_evidence: Mapped[str] = mapped_column(Text)
    related_evidence: Mapped[list] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    origin: Mapped[str] = mapped_column(String(40))
    origin_reference: Mapped[str | None] = mapped_column(String(200))
    access_scope: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    assigned_to: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_knowledge_id: Mapped[UUID | None] = mapped_column(ForeignKey("verified_knowledge.id"))
    resolution_document_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("document_versions.id"))
    resolution_note: Mapped[str | None] = mapped_column(Text)
