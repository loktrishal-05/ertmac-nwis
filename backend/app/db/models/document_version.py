"""Source revisions and durable ingestion state."""
import uuid
from sqlalchemy import ForeignKey, String, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, IdentityMixin, CreatedAtMixin


class DocumentVersion(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "document_versions"
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    source_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(40), default="processing")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    ingestion_metadata: Mapped[dict] = mapped_column(JSONB)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
