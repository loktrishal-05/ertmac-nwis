"""Local voice, descriptive BI and summary-only integration boundaries."""
from time import perf_counter
from typing import get_args
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session
from app.api.deps import require_role
from app.api.routes.verified_knowledge import transaction
from app.core.config import settings
from app.db.models import User
from app.db.session import get_db
from app.schemas.product import TranscriptionInput, SynthesisInput, AutomationInput, AutomationKind
from app.services import local_voice as voice, industrial_bi as bi, product_integration as integration
from app.services import language_resources as resources

router = APIRouter(tags=["product-integration"])
human = require_role("requester", "reviewer", "admin")
reviewer = require_role("reviewer", "admin")


@router.get("/product/status")
def status(response: Response, actor: User = Depends(human)):
    response.headers["Cache-Control"] = "no-store"
    return {"languages": voice.LANGUAGES, "translation": "disabled_original_preserved",
        # Existing values kept for the current frontend; *_health adds the live local probe.
        "stt": "configured_unverified" if voice.configured(settings.stt_url) else "unavailable",
        "tts": "configured_unverified" if voice.configured(settings.tts_url) else "unavailable",
        "stt_health": voice.health(settings.stt_url), "tts_health": voice.health(settings.tts_url),
        "audio_retention": "none", "transcript_retention": "not_stored_by_speech_endpoints", "text_mode": True,
        "speech_data_classification": "CONFIDENTIAL", "language_resources": resources.summary(),
        "automation": "configured_unverified" if integration.automation_configured() else "disabled",
        "automation_kinds": get_args(AutomationKind), "automation_authority": "summary_only"}


def speech(session, actor, kind, payload, operation):
    def run():
        start = perf_counter()
        try:
            result = operation()
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        # Metadata only: no audio, transcript or answer text enters the audit chain.
        integration.event(session, actor, kind, language=voice.language(payload.input_language),
            status=result["status"], reason=result.get("reason"), provider=result.get("provider"),
            identifier_count=len(result.get("technical_identifiers", [])),
            identifier_review_count=len(result.get("identifier_review", [])), latency_ms=(perf_counter()-start)*1000)
        return result
    return transaction(session, run)


@router.post("/voice/transcribe")
def transcribe(payload: TranscriptionInput, response: Response, actor: User = Depends(human), session: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return speech(session, actor, "stt", payload, lambda: voice.transcribe(payload.audio_base64, payload.mime_type, payload.input_language))


@router.post("/voice/synthesize")
def synthesize(payload: SynthesisInput, response: Response, actor: User = Depends(human), session: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return speech(session, actor, "tts", payload, lambda: voice.synthesize(payload.text, payload.input_language))


@router.get("/bi/operational")
def operational_bi(response: Response, actor: User = Depends(reviewer), session: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    def run():
        report = bi.snapshot(session)
        integration.event(session, actor, "bi_query", latency_ms=report["bi_latency_ms"])
        return report
    return transaction(session, run)


@router.post("/automation/webhook")
def webhook(payload: AutomationInput, response: Response, signature: str = Header(default="", alias="X-Workbench-Signature", max_length=64),
            session: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return transaction(session, lambda: integration.webhook(session, payload, signature))
