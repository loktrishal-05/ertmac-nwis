"""Document persistence model."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin, CreatedAtMixin


class Document(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "documents"

    filename: Mapped[str] = mapped_column(String(255))
    document_type: Mapped[str] = mapped_column(String(100))
    source_path: Mapped[str] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(50))
    checksum: Mapped[str | None] = mapped_column(String(128))
    ingestion_status: Mapped[str] = mapped_column(String(50), default="not_started", server_default="not_started")

