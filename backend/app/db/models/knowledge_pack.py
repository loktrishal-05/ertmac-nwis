"""Pack metadata binds to an A1 knowledge revision and its approval ledger."""
from uuid import UUID
from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, IdentityMixin, CreatedAtMixin

class KnowledgePack(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "knowledge_packs"
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(String(300))
    question: Mapped[str] = mapped_column(Text)
    match_key: Mapped[str] = mapped_column(String(64), index=True)
    knowledge_id: Mapped[UUID] = mapped_column(ForeignKey("verified_knowledge.id"), unique=True)
    members: Mapped[list] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
