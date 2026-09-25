"""Engine-neutral local HTTP adapters; audio stays in memory, no downloads."""
import base64
import binascii
import json
import httpx
from app.core.config import settings
from app.core.locality import classify_http_url, require_private_resolution

LANGUAGES = {"en": "English", "hi": "हिन्दी", "ta": "தமிழ்"}
MAX_AUDIO = 4 * 1024 * 1024
MIMES = {"audio/wav", "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4"}


def language(value):
    code = value.lower().split("-", 1)[0]
    return {"requested": value, "supported": code in LANGUAGES,
            "effective": code if code in LANGUAGES else "und",
            "translation": "disabled_original_preserved"}


def audio_bytes(value):
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("Invalid base64 audio") from error
    if not 0 < len(raw) <= MAX_AUDIO:
        raise ValueError("Audio must be between 1 byte and 4 MiB")
    return raw


def configured(url):
    return bool(url) and classify_http_url(url) != "invalid"


def exchange(url, payload):
    if not configured(url):
        raise ValueError("Local speech adapter unavailable")
    require_private_resolution(url)
    from app.services.model_gateway.observations import record_dispatch
    record_dispatch(classify_http_url(url))
    with httpx.Client(timeout=settings.speech_timeout_seconds, trust_env=False, follow_redirects=False) as client:
        with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 6 * 1024 * 1024:
                    raise ValueError("Speech response too large")
    return json.loads(data)


def transcribe(audio, mime, input_language):
    audio_bytes(audio)
    meta = language(input_language)
    try:
        result = exchange(settings.stt_url, {"audio_base64": audio, "mime_type": mime, "language": meta["effective"]})
        text = result["text"]
        if not isinstance(text, str) or not 0 < len(text.strip()) <= 10000:
            raise ValueError("Invalid transcript")
        return {"status": "ok", "text": text, "language": meta, "confirmation_required": True}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, OSError):
        return {"status": "unavailable", "text": None, "language": meta,
                "message": "Local STT unavailable. Continue in text mode."}


def synthesize(text, input_language):
    meta = language(input_language)
    try:
        result = exchange(settings.tts_url, {"text": "Advisory only. No permission to operate equipment. " + text,
                                             "language": meta["effective"]})
        audio_bytes(result["audio_base64"])
        if result["mime_type"] not in MIMES:
            raise ValueError("Unsupported audio type")
        return {"status": "ok", "audio_base64": result["audio_base64"], "mime_type": result["mime_type"], "language": meta}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, OSError):
        return {"status": "unavailable", "language": meta, "message": "Local TTS unavailable. Read the original text."}
