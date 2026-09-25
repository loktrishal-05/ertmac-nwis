"""Immutable-by-API human reports; review uses the existing approval ledger."""
from uuid import UUID
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, IdentityMixin, CreatedAtMixin

class OperatorNote(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "operator_notes"
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    equipment_id: Mapped[UUID] = mapped_column(ForeignKey("equipment.id"), index=True)
    unit: Mapped[str | None] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(40), default="operator_report")
    access_scope: Mapped[str] = mapped_column(String(50), default="internal")
    approval_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("action_revisions.id"))
