"""Local sessions, account recovery, and explicitly enabled connected authentication."""
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.core.config import settings
from app.core.security import hash_password, hash_session_token
from app.db.models import AuthIdentity, AuthSession, User
from app.db.session import get_db
from app.schemas.auth import AdminCreate, CodeRequest, EmailInput, Input, LoginRequest, ResetRequest, RoleRequest, SignupRequest, UserPublic
from app.services import accounts, auth_delivery, auth_oidc

router = APIRouter(tags=["auth"])
admin = require_role("admin")


def ip(request):
    return request.client.host if request.client else "unknown"


def set_cookie(response, token):
    response.set_cookie(settings.session_cookie_name, token, httponly=True, samesite="lax",
                        secure=settings.session_cookie_secure, max_age=int(settings.session_ttl_seconds), path="/")


@router.get("/auth/capabilities")
def capabilities():
    mode = settings.signup_mode
    if settings.deployment_mode == "confidential" and mode == "open":
        mode = "disabled"
    return {"local_login": True, "signup": mode != "disabled", "signup_mode": mode,
            "password_recovery": accounts.recovery_enabled(), "email_recovery": accounts.email_enabled(),
            "email_delivery": accounts.email_delivery(),
            "admin_recovery": accounts.recovery_enabled(), "google": auth_oidc.enabled()}


@router.post("/auth/signup", status_code=202)
def signup(payload: SignupRequest, request: Request, db: Session = Depends(get_db)):
    accounts.signup(db, payload, ip(request))
    return accounts.GENERIC


@router.post("/auth/login", response_model=UserPublic)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user, token = accounts.login(db, payload.username, payload.password, ip(request), request.cookies.get(settings.session_cookie_name))
    set_cookie(response, token)
    return user


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(settings.session_cookie_name)
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_session_token(token)).with_for_update()) if token else None
    if row and not row.revoked_at:
        row.revoked_at = accounts.now()
        accounts.event(db, "SESSIONS_REVOKED", db.get(User, row.user_id), count=1)
        db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"status": "logged_out"}


@router.get("/auth/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    providers = db.scalars(select(AuthIdentity.provider).where(AuthIdentity.user_id == user.id)).all()
    return {**UserPublic.model_validate(user).model_dump(), "linked_identities": providers}


@router.get("/auth/sessions")
def sessions(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current = hash_session_token(request.cookies.get(settings.session_cookie_name, ""))
    rows = db.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None),
        AuthSession.expires_at > accounts.now()).order_by(AuthSession.created_at.desc()).limit(100)).all()
    return [{"id": row.id, "created_at": row.created_at, "expires_at": row.expires_at,
             "current": row.token_hash == current} for row in rows]


@router.post("/auth/sessions/revoke-all")
def revoke_all(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.refresh(user, with_for_update=True)
    count = accounts.revoke_sessions(db, user.id)
    accounts.event(db, "SESSIONS_REVOKED", user, count=count)
    db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"status": "revoked"}


@router.post("/auth/sessions/{session_id}/revoke")
def revoke_one(session_id: UUID, request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(AuthSession).where(AuthSession.id == session_id, AuthSession.user_id == user.id).with_for_update())
    if row is None:
        raise HTTPException(404, "Session not found.")
    row.revoked_at = accounts.now()
    accounts.event(db, "SESSIONS_REVOKED", user, count=1)
    db.commit()
    if row.token_hash == hash_session_token(request.cookies.get(settings.session_cookie_name, "")):
        response.delete_cookie(settings.session_cookie_name, path="/")
    return {"status": "revoked"}


def dispatch_code(payload, request, background, db, purpose):
    delivery = accounts.request_code(db, payload.email, ip(request), purpose)
    if delivery:
        background.add_task(auth_delivery.deliver, *delivery, purpose)
    return accounts.GENERIC


@router.post("/auth/password/forgot", status_code=202)
def forgot(payload: EmailInput, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    return dispatch_code(payload, request, background, db, "password")


@router.post("/auth/email/request-verification", status_code=202)
def request_verification(payload: EmailInput, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    return dispatch_code(payload, request, background, db, "email")


@router.post("/auth/email/verify")
def verify_email(payload: CodeRequest, request: Request, db: Session = Depends(get_db)):
    return accounts.verify_code(db, payload, ip(request), "email")


@router.post("/auth/password/verify-otp")
def verify_otp(payload: CodeRequest, request: Request, db: Session = Depends(get_db)):
    return accounts.verify_code(db, payload, ip(request), "password")


@router.post("/auth/password/reset")
def reset_password(payload: ResetRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    accounts.reset_password(db, payload.reset_token, payload.new_password, ip(request))
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"status": "password_updated"}


@router.get("/auth/google/start")
def google_start(request: Request, db: Session = Depends(get_db)):
    url, binding = auth_oidc.start(db, ip(request))
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(auth_oidc.COOKIE, binding, httponly=True, secure=settings.session_cookie_secure,
                        samesite="lax", max_age=600, path="/")
    return response


@router.get("/auth/google/callback")
def google_callback(request: Request, code: str = Query(default="", max_length=4096),
                    state: str = Query(default="", max_length=128), db: Session = Depends(get_db)):
    if not auth_oidc.enabled():
        raise HTTPException(404, "Connected authentication is unavailable.")
    try:
        token, status = auth_oidc.callback(db, code, state, request.cookies.get(auth_oidc.COOKIE, ""), ip(request),
                                          request.cookies.get(settings.session_cookie_name))
    except HTTPException:
        db.rollback()
        token, status = None, "failed"
    response = RedirectResponse(settings.auth_frontend_origin.rstrip("/") + "/auth/callback?status=" + status, status_code=303)
    response.delete_cookie(auth_oidc.COOKIE, path="/")
    if token:
        set_cookie(response, token)
    return response


@router.get("/admin/users")
def list_users(offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
               pending: bool | None = None, actor: User = Depends(admin), db: Session = Depends(get_db)):
    statement = select(User).order_by(User.created_at, User.id).offset(offset).limit(limit)
    if pending is not None:
        statement = statement.where(User.signup_pending == pending)
    return [UserPublic.model_validate(user) for user in db.scalars(statement)]


@router.post("/admin/users", status_code=201, response_model=UserPublic)
def create_user(payload: AdminCreate, actor: User = Depends(admin), db: Session = Depends(get_db)):
    accounts.admin_lock(db)
    actor = accounts.admin_actor(db, actor.id)
    user = User(username=payload.username or "acct_" + uuid4().hex, display_name=payload.display_name,
                email=payload.email, role=payload.role, is_active=True, signup_pending=False, password_changed_at=accounts.now())
    accounts.password_policy(payload.password, user)
    user.password_hash = hash_password(payload.password)
    if payload.email and db.scalar(select(User.id).where(func.lower(User.username) == payload.email)):
        raise HTTPException(409, "Account identifier is already in use.")
    try:
        db.add(user)
        db.flush()
        accounts.event(db, "USER_CREATED", actor, target_user_id=user.id, role=user.role)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Account identifier is already in use.") from None
    return user


@router.post("/admin/users/{user_id}/role", response_model=UserPublic)
def change_role(user_id: UUID, payload: RoleRequest, actor: User = Depends(admin), db: Session = Depends(get_db)):
    return accounts.administer(db, actor.id, user_id, "role", payload.role)


@router.post("/admin/users/{user_id}/recovery")
def recovery(user_id: UUID, payload: Input | None = None, actor: User = Depends(admin), db: Session = Depends(get_db)):
    accounts.admin_lock(db)
    actor = accounts.admin_actor(db, actor.id)
    accounts.rate_guard(db, "admin-recovery", str(actor.id), 20)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Account not found.")
    issued = accounts.issue_code(db, user, "password", actor=actor)
    if not issued:
        db.commit()
        raise HTTPException(429, "Wait before issuing another code.")
    db.commit()
    return {"code": issued[1], "expires_in": 600, "username": user.username, "email": user.email}


@router.post("/admin/users/{user_id}/{operation}", response_model=UserPublic)
def change_user(user_id: UUID, operation: str, payload: Input | None = None, actor: User = Depends(admin), db: Session = Depends(get_db)):
    mapping = {"approve": "approve", "activate": "activate", "deactivate": "deactivate", "revoke-sessions": "revoke"}
    if operation not in mapping:
        raise HTTPException(404, "Operation not found.")
    return accounts.administer(db, actor.id, user_id, mapping[operation])
