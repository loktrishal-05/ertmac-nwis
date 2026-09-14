"""IncidentReport persistence model."""

import uuid
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin, CreatedAtMixin


class IncidentReport(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "incident_reports"

    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(50))
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("equipment.id"), index=True)

