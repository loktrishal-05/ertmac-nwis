"""Ingested maintenance/sensor CSV source tracking, for idempotency and provenance."""

from sqlalchemy import String, Integer, Text, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin, CreatedAtMixin

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class StructuredDataSource(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "structured_data_sources"

    source_type: Mapped[str] = mapped_column(String(20))
    source_filename: Mapped[str] = mapped_column(String(255))
    source_uri: Mapped[str] = mapped_column(Text)
    source_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(40), default="processing")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_row_count: Mapped[int] = mapped_column(Integer, default=0)
    ingestion_metadata: Mapped[dict] = mapped_column(JSONVariant)
    warnings: Mapped[list] = mapped_column(JSONVariant, default=list)
