"""Optional Google authorization-code OIDC; isolated from all inference paths."""
import base64
from datetime import timedelta
import hmac
import secrets
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import HTTPException
import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import hash_session_token
from app.db.models import AuthIdentity, OIDCFlow, User
from app.schemas.auth import normalized_email
from app.services import accounts as local

AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
JWKS = "https://www.googleapis.com/oauth2/v3/certs"
COOKIE = "workbench_oidc_binding"


def enabled():
    if settings.deployment_mode == "confidential" or not settings.google_enabled or not local.recovery_enabled():
        return False
    if settings.deployment_mode != "development" and not settings.session_cookie_secure:
        return False
    callback, frontend = urlsplit(settings.google_callback_url), urlsplit(settings.auth_frontend_origin)
    def safe(parts):
        return (not parts.username and not parts.password and not parts.query and not parts.fragment and parts.hostname and
                (parts.scheme == "https" or settings.deployment_mode == "development" and parts.scheme == "http" and
                 parts.hostname in {"localhost", "127.0.0.1", "::1"}))
    return bool(settings.google_client_id and settings.google_client_secret and safe(callback) and safe(frontend)
                and frontend.path in {"", "/"} and settings.auth_frontend_origin.rstrip("/") in settings.cors_origins)


def derived(label, state):
    return base64.urlsafe_b64encode(bytes.fromhex(local.secret_hash(label, state))).rstrip(b"=").decode()


def oauth_client():
    from authlib.integrations.httpx_client import OAuth2Client
    return OAuth2Client(settings.google_client_id, settings.google_client_secret, scope="openid email profile",
                        redirect_uri=settings.google_callback_url, code_challenge_method="S256",
                        timeout=10, trust_env=False, follow_redirects=False)


def start(db, ip):
    if not enabled():
        raise HTTPException(404, "Connected authentication is unavailable.")
    local.rate_guard(db, "oidc-start", ip, 20)
    state, binding = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(OIDCFlow(state_hash=hash_session_token(state), binding_hash=hash_session_token(binding),
                    expires_at=local.now() + timedelta(minutes=10)))
    with oauth_client() as client:
        url, _ = client.create_authorization_url(AUTHORIZE, state=state, nonce=derived("oidc-nonce", state),
                                                code_verifier=derived("oidc-pkce", state))
    db.commit()
    return url, binding


def read_json(response):
    response.raise_for_status()
    raw = bytearray()
    for chunk in response.iter_bytes():
        raw.extend(chunk)
        if len(raw) > 1024 * 1024:
            raise ValueError("OIDC response too large")
    import json
    return json.loads(raw)


def exchange(code, state):
    from authlib.jose import JsonWebToken
    with oauth_client() as client:
        # A bounded streamed exchange prevents provider bodies from consuming unbounded memory.
        with client.stream("POST", TOKEN, data={"grant_type": "authorization_code", "code": code,
                "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_callback_url, "code_verifier": derived("oidc-pkce", state)},
                withhold_token=True) as response:
            token = read_json(response)
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        with client.stream("GET", JWKS) as response:
            keys = read_json(response)
    claims = JsonWebToken(["RS256"]).decode(token["id_token"], keys, claims_options={
        "iss": {"essential": True, "values": ["https://accounts.google.com", "accounts.google.com"]},
        "aud": {"essential": True, "value": settings.google_client_id}, "exp": {"essential": True},
        "iat": {"essential": True}, "sub": {"essential": True},
        "nonce": {"essential": True, "value": derived("oidc-nonce", state)},
    })
    claims.validate(leeway=30)
    if (claims.get("azp") is not None and claims["azp"] != settings.google_client_id or
            isinstance(claims["aud"], list) and len(claims["aud"]) > 1 and claims.get("azp") != settings.google_client_id or
            claims.get("email_verified") is not True or not isinstance(claims["sub"], str) or not 1 <= len(claims["sub"]) <= 255):
        raise ValueError("Invalid provider claims")
    return dict(claims)


def consume_flow(db, state, binding, ip):
    if not enabled():
        raise HTTPException(404, "Connected authentication is unavailable.")
    local.rate_guard(db, "oidc-callback", ip, 30)
    flow = db.scalar(select(OIDCFlow).where(OIDCFlow.state_hash == hash_session_token(state))
                     .with_for_update().execution_options(populate_existing=True))
    if not flow or flow.consumed_at or local.utc(flow.expires_at) <= local.now() or not hmac.compare_digest(flow.binding_hash, hash_session_token(binding)):
        db.commit()
        raise HTTPException(400, "Connected sign-in could not be completed.")
    flow.consumed_at = local.now()
    db.commit()  # Consume before external exchange; provider errors cannot make state reusable.


def link(db, claims):
    subject, email = claims["sub"], normalized_email(claims["email"])
    identity = db.scalar(select(AuthIdentity).where(AuthIdentity.provider == "google", AuthIdentity.subject == subject))
    if identity:
        return db.scalar(select(User).where(User.id == identity.user_id).with_for_update())
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    if user:
        if not user.email_verified_at:
            raise HTTPException(409, "Sign in locally and verify your email before linking Google.")
        if db.scalar(select(AuthIdentity.id).where(AuthIdentity.user_id == user.id, AuthIdentity.provider == "google")):
            raise HTTPException(409, "Connected sign-in could not be completed.")
    else:
        if settings.signup_mode == "disabled":
            raise HTTPException(403, "Self-service signup is unavailable.")
        if db.scalar(select(User.id).where(func.lower(User.username) == email)):
            raise HTTPException(409, "Connected sign-in could not be completed.")
        name = str(claims.get("name", ""))[:100].strip()
        if not any(c.isalpha() for c in name) or any(ord(c) < 32 for c in name):
            name = "Google account"
        user = User(username="acct_" + uuid4().hex, email=email, display_name=name, role="requester",
                    email_verified_at=local.now(), is_active=settings.signup_mode == "open",
                    signup_pending=settings.signup_mode == "approval")
        db.add(user)
        db.flush()
        local.event(db, "USER_SIGNUP", user, provider="google", signup_mode=settings.signup_mode)
    db.add(AuthIdentity(user_id=user.id, provider="google", subject=subject))
    db.flush()
    local.event(db, "IDENTITY_LINKED", user, provider="google")
    return user


def callback(db, code, state, binding, ip, previous_token=None):
    consume_flow(db, state, binding, ip)
    try:
        claims = exchange(code, state)
        if claims.get("email_verified") is not True:
            raise ValueError("Email is unverified")
        claims["email"] = normalized_email(claims["email"])
    except Exception:
        raise HTTPException(400, "Connected sign-in could not be completed.") from None
    # Concurrent signup/link wins are re-read; never merge differing identities on conflict.
    for attempt in range(2):
        try:
            user = link(db, claims)
            if user.signup_pending or not user.is_active:
                db.commit()
                return None, "pending_or_inactive"
            token = local.issue_session(db, user, previous_token)
            db.commit()
            return token, "success"
        except IntegrityError:
            db.rollback()
            if attempt:
                raise HTTPException(409, "Connected sign-in could not be completed.") from None
