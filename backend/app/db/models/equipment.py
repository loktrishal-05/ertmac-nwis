"""Equipment persistence model."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin, CreatedAtMixin


class Equipment(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "equipment"

    equipment_tag: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    equipment_type: Mapped[str] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(255))

