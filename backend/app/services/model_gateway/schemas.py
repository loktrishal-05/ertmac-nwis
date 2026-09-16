"""Pydantic schema -> constrained-decoding JSON Schema (with every $defs/$ref
inlined), plus fence-stripped parse/validate. No new dependency: Pydantic is
used for both schema generation and validation.

Constrained decoding guarantees SYNTAX, not TRUTH: a schema-valid object can
still contain a fabricated citation or a wrong value. Grounding validation is
Phase 4B/4C work, not this module's job."""
import json
import re

from pydantic import BaseModel

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL)


def json_schema_for(schema: type[BaseModel]) -> dict:
    """model_json_schema() with every $ref resolved inline; no $defs/definitions
    section remains in the output. Required because nested agent schemas (Phase
    4B+) always produce $ref, and constrained decoding needs a self-contained schema."""
    raw = schema.model_json_schema()
    defs = raw.pop("$defs", None) or raw.pop("definitions", None) or {}
    return _inline(raw, defs)


def _inline(node, defs):
    if isinstance(node, dict):
        if set(node.keys()) == {"$ref"}:
            ref = node["$ref"]
            key = ref.rsplit("/", 1)[-1]
            if key not in defs:
                raise ValueError(f"Unresolvable JSON Schema reference: {ref}")
            return _inline(defs[key], defs)
        return {key: _inline(value, defs) for key, value in node.items()}
    if isinstance(node, list):
        return [_inline(item, defs) for item in node]
    return node


def strip_fence(text: str) -> str:
    """Strip one full wrapping ```json ... ``` (or bare ```) fence. Never
    extracts an embedded {...} from surrounding prose — prose outside the JSON
    object is a failure to be reported, not something to salvage."""
    match = _FENCE_RE.match(text)
    return match.group(1) if match else text


def parse_and_validate(text: str, schema: type[BaseModel]):
    """Raises json.JSONDecodeError on malformed/non-JSON text (including text
    with surrounding prose) or pydantic.ValidationError on a schema mismatch.
    The gateway turns either into the single bounded repair attempt."""
    stripped = strip_fence(text).strip()
    value = json.loads(stripped)
    return schema.model_validate(value)
