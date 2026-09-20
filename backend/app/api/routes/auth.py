"""Local/on-prem session authentication. No hosted identity provider, no
client-trusted header: a session is a server-issued opaque token, resolved
back to a verified principal on every request (see app.api.deps)."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import hash_session_token, new_session_token, verify_password
from app.db.models import AuthSession, User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserPublic)
def login(payload: LoginRequest, response: Response, session: Session = Depends(get_db)) -> UserPublic:
    user = session.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    # Same generic failure for "unknown user" and "wrong password": do not let
    # a client distinguish the two (username enumeration).
    if user is None or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = new_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.session_ttl_seconds)
    session.add(AuthSession(user_id=user.id, token_hash=hash_session_token(token), expires_at=expires_at))
    session.commit()

    response.set_cookie(
        key=settings.session_cookie_name, value=token, httponly=True, samesite="lax",
        secure=settings.session_cookie_secure, max_age=int(settings.session_ttl_seconds), path="/",
    )
    return UserPublic.model_validate(user)


@router.post("/logout")
def logout(response: Response, session: Session = Depends(get_db),
           session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name)) -> dict:
    if session_token:
        token_hash = hash_session_token(session_token)
        row = session.execute(select(AuthSession).where(AuthSession.token_hash == token_hash)).scalar_one_or_none()
        if row is not None and row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            session.commit()
    response.delete_cookie(key=settings.session_cookie_name, path="/")
    return {"status": "logged_out"}


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(user)
