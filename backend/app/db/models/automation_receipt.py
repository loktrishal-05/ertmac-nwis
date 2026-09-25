"""Durable webhook nonce; primary key prevents concurrent/restarted replay."""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, IdentityMixin, CreatedAtMixin


class AutomationReceipt(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "automation_receipts"
    kind: Mapped[str] = mapped_column(String(60))
