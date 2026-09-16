"""SensorReading persistence model."""

import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Float, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin, CreatedAtMixin


class SensorReading(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (
        UniqueConstraint("source_sha256", "source_row_number", name="uq_sensor_readings_source_row"),
    )

    equipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("equipment.id"), index=True)
    sensor_tag: Mapped[str] = mapped_column(String(100), index=True)
    sensor_type: Mapped[str] = mapped_column(String(100))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(50))
    quality: Mapped[str | None] = mapped_column(String(20))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_filename: Mapped[str] = mapped_column(String(255))
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_row_number: Mapped[int] = mapped_column(Integer)
