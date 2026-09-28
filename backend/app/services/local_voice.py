"""Engine-neutral local HTTP adapters: audio stays in memory (never on disk), no downloads, no hosted fallback.

Runtime contract (any local engine behind a small HTTP shim):
  POST STT_URL  {"audio_base64", "mime_type", "language"} -> {"text", "confidence"?, "words"?: [{"text", "confidence"}], "language"?}
  POST TTS_URL  {"text", "language"} -> {"audio_base64", "mime_type"}
  GET  <origin>/health -> 200 when ready
"""
import base64
import binascii
import json
import re
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.core.locality import classify_http_url, require_private_resolution
from app.services.language_resources import PolicyDenied, speech_provider
from app.services.pid_identifiers import PID_PATTERNS

LANGUAGES = {"en": "English", "hi": "हिन्दी", "ta": "தமிழ்"}
MAX_AUDIO = 4 * 1024 * 1024
MIMES = {"audio/wav", "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4"}
# The declared MIME type must match the container bytes.
SIGNATURES = {
    "audio/wav": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WAVE",
    "audio/webm": lambda b: b[:4] == b"\x1aE\xdf\xa3",
    "audio/ogg": lambda b: b[:4] == b"OggS",
    "audio/mpeg": lambda b: b[:3] == b"ID3" or (len(b) > 1 and b[0] == 0xFF and b[1] & 0xE0 == 0xE0),
    "audio/mp4": lambda b: b[4:8] == b"ftyp",
}
BOUNDARY = "Advisory only. No permission to operate equipment. "
UNITS = r"mm/s|m/s|mm|µm|um|barg|bar|kPa|MPa|psi|°C|degC|rpm|Hz|kW|MW|kV|V|A|%|m3/h|m³/h|kg/h|t/h|L/min|mg/L|ppm"
DOCUMENT_PREFIXES = ("SOP", "WO", "DOC", "MOC", "PTW", "WI", "DWG")
# Detected and reported, never rewritten or translated.
IDENTIFIERS = {
    "equipment_tag": PID_PATTERNS["equipment_tags"],
    "instrument_tag": PID_PATTERNS["instrument_tags"],
    "document_id": rf"(?<![A-Z0-9-])(?:{'|'.join(DOCUMENT_PREFIXES)})(?:-[A-Z0-9]+){{1,4}}(?![A-Z0-9-])",
    "measurement": rf"(?<![\w.-])\d+(?:\.\d+)?\s?(?:{UNITS})(?![\w/])",
}
# Relax only separators in the established tag grammar; never normalize the transcript.
NEAR_TAGS = [re.compile(IDENTIFIERS[kind].replace(
    r"-\d{2,5}[A-Z]?", r"[- \t]{0,3}\d{2,5}(?:[- \t]{0,3}[A-Z](?![A-Z]))?"), re.I)
    for kind in ("equipment_tag", "instrument_tag")]
NEAR_DOCUMENT = re.compile(
    r"(?<![\w-])([A-Z]{2,3})[- \t]{0,3}(?:[A-Z]{1,4})?\d{2,5}[A-Z]?"
    r"(?:[- \t]{1,3}(?:[A-Z]{1,4})?\d{2,5}[A-Z]?){0,3}(?![\w-])", re.I)
ORPHAN_TAG = re.compile(r"(?<![\w.-])\d{2,5}[A-Z](?![\w-])", re.I)
RATE_UNITS = "|".join(re.escape(unit).replace("/", r"[- \t]{1,3}")
                      for unit in UNITS.split("|") if "/" in unit)
NEAR_UNIT = re.compile(rf"(?<![\w.-])\d+(?:\.\d+)?\s?(?:{RATE_UNITS})(?![\w/])", re.I)
SPOKEN_UNIT = re.compile(
    r"(?<![\w.])\d{1,5}(?:[ \t]+point[ \t]+\d{1,5})?[ \t]+"
    r"(?:milli)?met(?:er|re)s?[ \t]+per[ \t]+second(?!\w)", re.I)


def suspicious_identifiers(text, found):
    """Bounded structural warnings only. No registry lookup, inferred tag or correction."""
    matches = []
    for pattern in NEAR_TAGS:
        for match in pattern.finditer(text):
            if not any(re.fullmatch(IDENTIFIERS[k], match.group(), re.I)
                       for k in ("equipment_tag", "instrument_tag")):
                reason = "possible_split_identifier" if " " in match.group() else "malformed_identifier"
                matches.append((match, reason))
    for match in NEAR_DOCUMENT.finditer(text):
        prefix = match[1].upper()
        # At most one substitution in a known prefix, only beside a numeric ID shape.
        if prefix in DOCUMENT_PREFIXES:
            if not re.fullmatch(IDENTIFIERS["document_id"], match.group(), re.I):
                matches.append((match, "malformed_document_identifier"))
        elif any(len(prefix) == len(p) and sum(a != b for a, b in zip(prefix, p)) == 1
                 for p in DOCUMENT_PREFIXES):
            matches.append((match, "possible_document_prefix"))
    for pattern, reason in ((ORPHAN_TAG, "possible_identifier_fragment"),
                            (NEAR_UNIT, "suspicious_engineering_unit"),
                            (SPOKEN_UNIT, "spoken_engineering_measurement")):
        matches.extend((m, reason) for m in pattern.finditer(text))
    result = []
    # ponytail: overlap scans are quadratic on at most 10k characters; index spans if that limit grows.
    for match, reason in sorted(matches, key=lambda item: (item[0].start(), -item[0].end())):
        if any(i["start"] <= match.start() and match.end() <= i["end"]
               for i in found if i["kind"] != "measurement"):
            continue
        if any(i["start"] <= match.start() and match.end() <= i["end"] for i in result):
            continue
        result.append({"text": match.group(), "kind": "possible_identifier", "start": match.start(),
                       "end": match.end(), "reasons": [reason]})
    return result


def language(value):
    code = value.lower().split("-", 1)[0]
    return {"requested": value, "supported": code in LANGUAGES,
            "effective": code if code in LANGUAGES else "und",
            "translation": "disabled_original_preserved"}


def audio_bytes(value, mime=None):
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("Invalid base64 audio") from error
    if not 0 < len(raw) <= MAX_AUDIO:
        raise ValueError("Audio must be between 1 byte and 4 MiB")
    if mime is not None and (mime not in SIGNATURES or not SIGNATURES[mime](raw)):
        raise ValueError("Audio content does not match the declared type")
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


def health(url):
    """Probe <origin>/health on the same loopback/private host; any failure is 'unavailable'."""
    if not configured(url):
        return "unavailable"
    parts = urlsplit(url)
    probe = f"{parts.scheme}://{parts.netloc}/health"
    try:
        require_private_resolution(probe)
        with httpx.Client(timeout=min(5, settings.speech_timeout_seconds), trust_env=False, follow_redirects=False) as client:
            return "ready" if client.get(probe).status_code == 200 else "unavailable"
    except (httpx.HTTPError, OSError, ValueError):
        return "unavailable"


def identifiers(text):
    found = []
    for kind, pattern in IDENTIFIERS.items():
        for match in re.finditer(pattern, text, re.I):
            found.append({"text": match.group(), "kind": kind, "start": match.start(), "end": match.end()})
    return sorted(found, key=lambda item: item["start"])


def identifier_review(text, words=(), confidence=None, threshold=None):
    """Identifiers a human should check before submitting; the transcript itself is never changed."""
    threshold = settings.stt_identifier_min_confidence if threshold is None else threshold
    spans, cursor = [], 0
    for word in words:  # Locate each recognised word in order to get its character span.
        start = text.find(word["text"], cursor)
        if start >= 0:
            spans.append((start, start + len(word["text"]), word["confidence"]))
            cursor = start + len(word["text"])
    found = identifiers(text)
    review = []
    for item in found:
        reasons = []
        if item["kind"] != "measurement" and item["text"] != item["text"].upper():
            reasons.append("non_canonical_case")
        if any(s < item["end"] and item["start"] < e and c < threshold for s, e, c in spans):
            reasons.append("low_word_confidence")
        elif not spans and confidence is not None and confidence < threshold:
            reasons.append("low_transcript_confidence")
        if reasons:
            review.append({**item, "reasons": reasons})
    review.extend(suspicious_identifiers(text, found))
    for item in review:
        item.update(raw_span=text[item["start"]:item["end"]], review_required=True,
                    confirmation_required=True, candidates=[])
    return sorted(review, key=lambda item: item["start"])


def _words(result):
    words = result.get("words") or []
    if not isinstance(words, list) or not all(isinstance(w, dict) and isinstance(w.get("text"), str)
            and isinstance(w.get("confidence"), (int, float)) and 0 <= w["confidence"] <= 1 for w in words):
        raise ValueError("Invalid word confidences")
    confidence = result.get("confidence")
    if confidence is not None and (not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
        raise ValueError("Invalid transcript confidence")
    return words, confidence


def _unavailable(base, url, error, message):
    if isinstance(error, PolicyDenied):
        reason = "policy_denied"
    elif isinstance(error, httpx.TimeoutException):
        reason = "timeout"
    elif isinstance(error, (httpx.HTTPError, OSError)):
        reason = "runtime_unavailable"
    else:
        reason = "invalid_response" if configured(url) else "not_configured"
    return {**base, "status": "unavailable", "reason": reason, "message": message}


def transcribe(audio, mime, input_language):
    audio_bytes(audio, mime)  # Invalid input is a 422, not an adapter outage.
    meta = language(input_language)
    base = {"text": None, "language": meta, "confirmation_required": True, "fallback": "editable_text", "provider": None}
    try:
        base["provider"] = speech_provider("stt")
        result = exchange(settings.stt_url, {"audio_base64": audio, "mime_type": mime, "language": meta["effective"]})
        text = result["text"]
        if not isinstance(text, str) or not 0 < len(text.strip()) <= 10000:
            raise ValueError("Invalid transcript")
        words, confidence = _words(result)
    except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return _unavailable(base, settings.stt_url, error, "Local STT unavailable. Continue in text mode.")
    detected = result.get("language")
    review = identifier_review(text, words, confidence)
    return {**base, "status": "ok", "text": text, "original_text": text, "translated_text": None,
            "detected_language": detected if isinstance(detected, str) else None, "confidence": confidence,
            "technical_identifiers": identifiers(text), "identifier_review": review, "review_required": bool(review),
            "review_message": "Review the original transcript and verify all tags, document IDs and measurements before submitting."}


def synthesize(text, input_language):
    """Presentation only: the answer text is returned unchanged whatever happens to the audio."""
    meta = language(input_language)
    base = {"text": text, "language": meta, "fallback": "text", "provider": None}
    if not meta["supported"]:
        return {**base, "status": "unsupported_language",
                "message": "Speech is not available for this language. Read the original text."}
    try:
        base["provider"] = speech_provider("tts")
        result = exchange(settings.tts_url, {"text": BOUNDARY + text, "language": meta["effective"]})
        if result["mime_type"] not in MIMES:
            raise ValueError("Unsupported audio type")
        audio_bytes(result["audio_base64"], result["mime_type"])
    except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return _unavailable(base, settings.tts_url, error, "Local TTS unavailable. Read the original text.")
    return {**base, "status": "ok", "audio_base64": result["audio_base64"], "mime_type": result["mime_type"]}
