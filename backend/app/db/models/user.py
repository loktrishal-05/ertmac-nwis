"""User persistence model.

Phase 5B roles (app-level convention, not a DB CHECK constraint -- see
docs/phase5b.md): "requester" (default; may originate governed /query
requests), "reviewer" (may approve/reject/revoke), "admin" (reviewer plus any
elevated rights documented in docs/phase5b.md). Nothing here grants those
roles authority by itself; app.api.deps enforces them per request.
"""

from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin, CreatedAtMixin


class User(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True)
    role: Mapped[str] = mapped_column(String(50), default="requester", server_default="requester")
    # Argon2id hash (app.core.security.hash_password); never a plaintext password,
    # and never logged. Nullable: an account with no hash cannot authenticate.
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    email: Mapped[str | None] = mapped_column(String(254))
    display_name: Mapped[str | None] = mapped_column(String(100))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    signup_pending: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("uq_users_email_normalized", func.lower(email), unique=True),
        CheckConstraint("email IS NULL OR email = lower(trim(email))", name="email_normalized"),
    )
