"""User persistence model.

Phase 5B roles (app-level convention, not a DB CHECK constraint -- see
docs/phase5b.md): "requester" (default; may originate governed /query
requests), "reviewer" (may approve/reject/revoke), "admin" (reviewer plus any
elevated rights documented in docs/phase5b.md). Nothing here grants those
roles authority by itself; app.api.deps enforces them per request.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin, CreatedAtMixin


class User(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True)
    role: Mapped[str] = mapped_column(String(50), default="requester", server_default="requester")
    # Argon2id hash (app.core.security.hash_password); never a plaintext password,
    # and never logged. Nullable: an account with no hash cannot authenticate.
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
