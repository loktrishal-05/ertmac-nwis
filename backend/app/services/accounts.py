"""Local account operations. Caller owns transactions; no credentials enter audit payloads."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import hash_password, hash_session_token, new_session_token, verify_password
from app.db.models import AuthAttempt, AuthChallenge, AuthSession, ResetCapability, User
from app.schemas.auth import normalized_email
from app.services.audit import append_event

GENERIC = {"status": "accepted", "message": "If the request is eligible, further instructions will be provided."}
DUMMY_PASSWORD = hash_password("dummy-account-verification-not-a-login-password")
COMMON_PASSWORDS = frozenset({"password", "password123", "password1234", "123456789012", "qwertyuiopas",
    "administrator", "welcome12345", "letmein12345", "iloveyou1234", "sovereign123"})


def now():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def event(db, kind, actor=None, **payload):
    append_event(db, event_type=kind, actor_id=actor.id if actor else None,
                 actor_kind="user" if actor else "anonymous", payload=payload)


def failure_event(db, identifier):
    # A failed audit append must not roll back the attempt counter.
    try:
        with db.begin_nested():
            event(db, "LOGIN_FAILURE", identifier_hash=hash_session_token(identifier.lower()))
    except Exception:
        pass


def secret_hash(purpose, value):
    if len(settings.auth_secret.encode()) < 32:
        raise HTTPException(503, "Recovery is not configured.")
    return hmac.new(settings.auth_secret.encode(), (purpose + ":" + value).encode(), hashlib.sha256).hexdigest()


def recovery_enabled():
    return len(settings.auth_secret.encode()) >= 32


def email_enabled():
    return recovery_enabled() and bool(settings.smtp_host and settings.smtp_sender)


def budget(db, scope, identifier, limit, seconds=900):
    """Atomic fixed-window budget, including unknown identifiers; shared across workers."""
    stamp = now()
    key = hash_session_token(scope + ":" + identifier.lower())
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    statement = insert(AuthAttempt).values(key=key, count=1, expires_at=stamp + timedelta(seconds=seconds))
    statement = statement.on_conflict_do_update(index_elements=[AuthAttempt.key], set_={
        "count": case((AuthAttempt.expires_at <= stamp, 1), else_=AuthAttempt.count + 1),
        "expires_at": case((AuthAttempt.expires_at <= stamp, stamp + timedelta(seconds=seconds)), else_=AuthAttempt.expires_at),
    }).returning(AuthAttempt.count)
    return db.scalar(statement) <= limit


def rate_guard(db, scope, identifier, limit, seconds=900):
    if not budget(db, scope, identifier, limit, seconds):
        db.commit()
        raise HTTPException(429, "Too many attempts. Try again later.")


def password_policy(password, user):
    words = [part for part in (user.display_name or "").lower().split() if len(part) >= 3]
    email_part = (user.email or "").split("@")[0]
    if len(email_part) >= 3:
        words.append(email_part)
    if not 12 <= len(password) <= 128 or password.lower() in COMMON_PASSWORDS or any(p in password.lower() for p in words):
        raise HTTPException(422, "Use 12–128 characters, avoiding common passwords and your name or email.")


def lookup(db, identifier, *, lock=False):
    try:
        email = normalized_email(identifier)
    except ValueError:
        email = None
    statement = select(User).where(or_(User.username == identifier, User.email == email if email else False))
    if lock:
        statement = statement.with_for_update()
    users = db.scalars(statement.execution_options(populate_existing=True)).all()
    return users[0] if len(users) == 1 else None


def revoke_sessions(db, user_id):
    return db.execute(update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
                      .values(revoked_at=now())).rowcount


def issue_session(db, user, previous_token=None):
    # Lock the account to serialize against password reset/deactivation/role changes.
    db.refresh(user, with_for_update=True)
    if not user.is_active or user.signup_pending:
        raise HTTPException(401, "Invalid username or password.")
    if previous_token:
        db.execute(update(AuthSession).where(AuthSession.token_hash == hash_session_token(previous_token),
                   AuthSession.revoked_at.is_(None)).values(revoked_at=now()))
    token = new_session_token()
    db.add(AuthSession(user_id=user.id, token_hash=hash_session_token(token),
                       expires_at=now() + timedelta(seconds=settings.session_ttl_seconds)))
    user.last_login_at = now()
    user.failed_login_attempts = 0
    user.locked_until = None
    event(db, "LOGIN_SUCCESS", user, username=user.username)
    return token


def login(db, identifier, password, ip, previous_token=None):
    rate_guard(db, "login-ip", ip, 30)
    allowed = budget(db, "login-identifier", identifier, 10)
    user = lookup(db, identifier, lock=True)
    checked = verify_password(password, user.password_hash if user and user.password_hash else DUMMY_PASSWORD)
    valid = checked and bool(user and user.password_hash)
    locked = user and user.locked_until and utc(user.locked_until) > now()
    if not allowed or not user or not valid or not user.is_active or user.signup_pending or locked:
        if user and not valid:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 10:
                user.locked_until = now() + timedelta(minutes=15)
                user.failed_login_attempts = 0
        failure_event(db, identifier)
        db.commit()
        raise HTTPException(401, "Invalid username or password.")
    token = issue_session(db, user, previous_token)
    db.commit()
    return user, token


def signup(db, payload, ip):
    if settings.signup_mode == "disabled" or (settings.deployment_mode == "confidential" and settings.signup_mode == "open"):
        raise HTTPException(403, "Self-service signup is unavailable.")
    rate_guard(db, "signup-ip", ip, 5, 3600)
    user = User(username="acct_" + uuid4().hex, display_name=payload.display_name, email=payload.email,
                role="requester", is_active=settings.signup_mode == "open", signup_pending=settings.signup_mode == "approval",
                password_changed_at=now())
    password_policy(payload.password, user)
    user.password_hash = hash_password(payload.password)
    # Refuse a new email that would make a preserved legacy username ambiguous.
    exists = db.scalar(select(User.id).where(or_(User.email == payload.email, func.lower(User.username) == payload.email)))
    if exists:
        db.commit()
        return
    try:
        with db.begin_nested():
            db.add(user)
            db.flush()
    except IntegrityError:
        db.commit()
        return
    event(db, "USER_SIGNUP", user, signup_mode=settings.signup_mode)
    db.commit()


def issue_code(db, user, purpose, *, delivery=False, actor=None):
    secret_hash("configuration", "check")
    db.refresh(user, with_for_update=True)
    latest = db.scalar(select(AuthChallenge).where(AuthChallenge.user_id == user.id, AuthChallenge.purpose == purpose)
                       .order_by(AuthChallenge.created_at.desc(), AuthChallenge.id.desc()).limit(1))
    if latest and (now() - utc(latest.created_at)).total_seconds() < 60:
        return None
    stamp = now()
    db.execute(update(AuthChallenge).where(AuthChallenge.user_id == user.id, AuthChallenge.purpose == purpose,
               AuthChallenge.consumed_at.is_(None)).values(consumed_at=stamp))
    if purpose == "password":
        db.execute(update(ResetCapability).where(ResetCapability.user_id == user.id, ResetCapability.consumed_at.is_(None))
                   .values(consumed_at=stamp))
    code = f"{secrets.randbelow(1000000):06d}"
    challenge = AuthChallenge(id=uuid4(), user_id=user.id, purpose=purpose, created_at=stamp,
        expires_at=stamp + timedelta(minutes=10), code_hash="", attempts=0, email_delivery=delivery)
    challenge.code_hash = secret_hash("code", f"{challenge.id}:{purpose}:{code}")
    db.add(challenge)
    kind = "ADMIN_RECOVERY_ISSUED" if actor else ("PASSWORD_RESET_REQUESTED" if purpose == "password" else "EMAIL_VERIFICATION_REQUESTED")
    event(db, kind, actor, target_user_id=user.id, challenge_id=challenge.id)
    return challenge, code


def request_code(db, email, ip, purpose):
    if not email_enabled():
        return None
    allowed_ip = budget(db, purpose + "-request-ip", ip, 20)
    if not allowed_ip:
        db.commit()
        return None
    allowed_id = budget(db, purpose + "-request-id", email, 3)
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    eligible = user and (purpose == "email" and not user.email_verified_at or
                         purpose == "password" and user.email_verified_at and user.is_active and not user.signup_pending)
    issued = issue_code(db, user, purpose, delivery=True) if allowed_ip and allowed_id and eligible else None
    db.commit()
    return (user.email, issued[0].id, issued[1]) if issued else None


def verify_code(db, payload, ip, purpose):
    secret_hash("configuration", "check")
    identifier = payload.email if payload.email is not None else payload.username
    rate_guard(db, purpose + "-verify-ip", ip, 20)
    rate_guard(db, purpose + "-verify-id", identifier, 10)
    user = lookup(db, identifier, lock=True)
    challenge = db.scalar(select(AuthChallenge).where(AuthChallenge.user_id == user.id,
        AuthChallenge.purpose == purpose, AuthChallenge.consumed_at.is_(None))
        .order_by(AuthChallenge.created_at.desc()).with_for_update().limit(1)) if user else None
    valid = False
    if challenge and utc(challenge.expires_at) > now() and challenge.attempts < 5:
        challenge.attempts += 1
        valid = hmac.compare_digest(challenge.code_hash, secret_hash("code", f"{challenge.id}:{purpose}:{payload.code}"))
        if purpose == "email" and not challenge.email_delivery:
            valid = False
    if not valid:
        db.commit()
        raise HTTPException(400, "Code is invalid or expired.")
    challenge.consumed_at = now()
    if purpose == "email":
        user.email_verified_at = now()
        event(db, "EMAIL_VERIFIED", user)
        result = {"status": "verified"}
    else:
        token = new_session_token()
        db.add(ResetCapability(user_id=user.id, token_hash=hash_session_token(token), expires_at=now() + timedelta(minutes=10)))
        event(db, "PASSWORD_RESET_VERIFIED", user, challenge_id=challenge.id)
        result = {"reset_token": token, "expires_in": 600}
    db.commit()
    return result


def reset_password(db, token, password, ip):
    rate_guard(db, "reset-ip", ip, 20)
    # Discover owner, then lock user before token consistently with issue/verify.
    owner = db.scalar(select(ResetCapability.user_id).where(ResetCapability.token_hash == hash_session_token(token)))
    user = db.scalar(select(User).where(User.id == owner).with_for_update()) if owner else None
    grant = db.scalar(select(ResetCapability).where(ResetCapability.token_hash == hash_session_token(token))
                      .with_for_update().execution_options(populate_existing=True))
    if not user or not grant or grant.consumed_at or utc(grant.expires_at) <= now():
        db.commit()
        raise HTTPException(400, "Reset capability is invalid or expired.")
    password_policy(password, user)
    user.password_hash = hash_password(password)
    user.password_changed_at = now()
    user.failed_login_attempts = 0
    user.locked_until = None
    db.execute(update(ResetCapability).where(ResetCapability.user_id == user.id, ResetCapability.consumed_at.is_(None))
               .values(consumed_at=now()))
    db.execute(update(AuthChallenge).where(AuthChallenge.user_id == user.id, AuthChallenge.consumed_at.is_(None))
               .values(consumed_at=now()))
    revoked = revoke_sessions(db, user.id)
    event(db, "PASSWORD_RESET_COMPLETED", user, sessions_revoked=revoked)
    db.commit()


def admin_lock(db):
    # ponytail: one transaction lock for rare membership edits; partition only for separate tenants.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(170017)"))


def admin_actor(db, actor_id):
    actor = db.scalar(select(User).where(User.id == actor_id).execution_options(populate_existing=True))
    if not actor or not actor.is_active or actor.signup_pending or actor.role != "admin":
        raise HTTPException(403, "Not authorized for this action.")
    return actor


def administer(db, actor_id, target_id, operation, role=None):
    admin_lock(db)
    actor = admin_actor(db, actor_id)
    user = db.scalar(select(User).where(User.id == target_id).with_for_update().execution_options(populate_existing=True))
    if not user:
        raise HTTPException(404, "Account not found.")
    if operation in {"role", "deactivate"} and actor.id == user.id:
        raise HTTPException(409, "Cannot change your own role or deactivate yourself.")
    removing_admin = user.role == "admin" and user.is_active and (operation == "deactivate" or operation == "role" and role != "admin")
    if removing_admin and db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True), User.signup_pending.is_(False))) <= 1:
        raise HTTPException(409, "The final active administrator must be preserved.")
    if operation == "approve":
        if not user.signup_pending:
            raise HTTPException(409, "Account is not pending approval.")
        user.signup_pending, user.is_active = False, True
        kind = "SIGNUP_APPROVED"
    elif operation == "activate":
        if user.signup_pending:
            raise HTTPException(409, "Pending signup requires approval.")
        user.is_active, kind = True, "USER_ACTIVATED"
    elif operation == "deactivate":
        user.is_active, kind = False, "USER_DEACTIVATED"
    elif operation == "role":
        user.role, kind = role, "USER_ROLE_CHANGED"
    else:
        kind = "SESSIONS_REVOKED"
    revoked = revoke_sessions(db, user.id) if operation in {"role", "deactivate", "revoke"} else 0
    event(db, kind, actor, target_user_id=user.id, role=user.role, sessions_revoked=revoked)
    db.commit()
    return user
