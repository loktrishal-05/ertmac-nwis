"""Server-verified authentication/authorization dependencies.

A request BODY can never choose its authenticated user: every dependency
here resolves identity only from a server-issued session cookie, hashed and
looked up against app.db.models.AuthSession. There is no X-User-ID header,
no client-supplied role, and no client-trusted provider identity claim."""
from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_session_token
from app.db.models import AuthSession, User
from app.db.session import get_db


def get_optional_current_user(
    session: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> User | None:
    if not session_token:
        return None
    token_hash = hash_session_token(session_token)
    row = session.execute(
        select(AuthSession).where(AuthSession.token_hash == token_hash)
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        return None
    user = session.get(User, row.user_id)
    return user if user is not None and user.is_active and not user.signup_pending else None


def get_current_user(user: User | None = Depends(get_optional_current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def require_role(*roles: str):
    """A dependency factory: 403s a user whose (server-loaded) role is not
    one of `roles`. Never reads a role from the request body or headers."""
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Not authorized for this action.")
        return user
    return _check
