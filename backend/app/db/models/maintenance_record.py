"""MaintenanceRecord persistence model; rows parsed from maintenance CSV sources."""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Float, DateTime, Integer, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin, CreatedAtMixin

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class MaintenanceRecord(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "maintenance_records"
    __table_args__ = (
        UniqueConstraint("source_sha256", "source_row_number", name="uq_maintenance_records_source_row"),
    )

    equipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("equipment.id"), index=True)
    raw_equipment_tag: Mapped[str] = mapped_column(String(100))
    work_order_id: Mapped[str | None] = mapped_column(String(100), index=True)
    maintenance_type: Mapped[str | None] = mapped_column(String(50))
    failure_mode: Mapped[str | None] = mapped_column(String(255))
    maintenance_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    downtime_hours: Mapped[float | None] = mapped_column(Float)
    parts_replaced: Mapped[str | None] = mapped_column(Text)
    technician_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(50))
    source_filename: Mapped[str] = mapped_column(String(255))
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_row_number: Mapped[int] = mapped_column(Integer)
    raw_row: Mapped[dict] = mapped_column(JSONVariant)
