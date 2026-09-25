"""Scoped integration events and authenticated summary-only automation."""
import hashlib
import hmac
import time
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.db.models import AutomationReceipt, User
from app.services.audit import append_event
from app.services.verified_knowledge import authorize
from app.services.industrial_bi import snapshot


def event(session, actor, kind, **metrics):
    append_event(session, event_type="PRODUCT_INTEGRATION_EVENT", actor_id=actor.id,
        actor_kind="user", payload={"kind": kind, **metrics})


def signature(payload, secret):
    message = f"{payload.timestamp}.{payload.nonce}.{payload.kind}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def automation_configured():
    return len(settings.automation_secret) >= 32 and bool(settings.automation_user_id)


def webhook(session, payload, supplied_signature):
    if not automation_configured():
        raise HTTPException(503, "Automation disabled")
    if abs(time.time() - payload.timestamp) > 300 or not hmac.compare_digest(signature(payload, settings.automation_secret), supplied_signature):
        raise HTTPException(401, "Invalid or expired webhook signature")
    try:
        actor = session.get(User, UUID(settings.automation_user_id))
    except ValueError:
        raise HTTPException(503, "Automation principal is not configured correctly")
    authorize(session, actor, review=True)
    try:
        with session.begin_nested():
            session.add(AutomationReceipt(id=payload.nonce, kind=payload.kind))
            session.flush()
    except IntegrityError:
        raise HTTPException(409, "Webhook nonce already consumed")
    report = snapshot(session)
    event(session, actor, "n8n_webhook", workflow=payload.kind, nonce=str(payload.nonce), bi_latency_ms=report["bi_latency_ms"])
    # No query execution, approvals, destinations, notifications or arbitrary actions.
    return {"kind": payload.kind, "nonce": str(payload.nonce), "status": "summary_ready",
            "advisory_only": True, "delivery_performed": False, "report": report}
