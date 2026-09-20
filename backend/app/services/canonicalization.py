"""Workbench JSON v1, not RFC 8785/JCS. Hash exactly the stored UTF-8 text."""
import hashlib
import json
import math
from datetime import datetime, timezone
from uuid import UUID

CANONICALIZATION_VERSION = "workbench-json-v1"


def _normalize(value):
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Canonical payloads cannot contain NaN or infinity")
        return int(value) if value.is_integer() else value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Canonical timestamps must have an explicit timezone")
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, UUID):
        return str(value)
    if type(value) is list:
        return [_normalize(item) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _normalize(item) for key, item in value.items()}
    raise ValueError("Unsupported canonical payload type")


def canonical_json(payload) -> str:
    serialized = json.dumps(
        {"canonicalization_version": CANONICALIZATION_VERSION, "payload": _normalize(payload)},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    serialized.encode("utf-8")  # Reject lone surrogates before persisting text.
    return serialized


def canonical_hash(payload) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
