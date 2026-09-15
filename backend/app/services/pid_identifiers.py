"""Conservative deterministic OCR normalization; never guess O/0 or I/1."""
import re
import unicodedata
from app.services.tags import DEFAULT_PATTERNS, extract_tags

PID_PATTERNS = DEFAULT_PATTERNS | {
    "instrument_tags": DEFAULT_PATTERNS["instrument_tags"].replace("(?:FV|", "(?:XV|NRV|FV|")
}


def normalize_identifier(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).upper()
    value = value.translate(str.maketrans({char: "-" for char in "‐‑‒–—−"}))
    value = re.sub(r"\s*-\s*", "-", value)
    # Repair whitespace only within a recognizable identifier shape, not arbitrary prose.
    value = re.sub(r"\b([A-Z]{1,3}-\d{2,5})\s+([A-Z])\b", r"\1\2", value)
    return " ".join(value.split())


def classify_text(text: str):
    normalized = normalize_identifier(text)
    tags = extract_tags(normalized, PID_PATTERNS)
    tags["valve_tags"] = [tag for tag in tags["instrument_tags"]
                          if re.match(r"^(?:XV|NRV|FV|LV|PV|TV|PSV)-", tag)]
    category = "other_text"
    if normalized in tags["valve_tags"]:
        category = "valve_tag"
    elif normalized in tags["equipment_tags"]:
        category = "equipment_tag"
    elif normalized in tags["instrument_tags"]:
        category = "instrument_tag"
    elif normalized in tags["line_numbers"]:
        category = "line_number"
    elif re.fullmatch(r"[+-]?\d+(?:\.\d+)?\s*°?\s*(?:C|F|K)", normalized):
        category = "temperature_value"
    elif re.fullmatch(r"[+-]?\d+(?:\.\d+)?\s*(?:BAR(?:G|A)?|KPA|MPA|PA|PSI(?:G|A)?)", normalized):
        category = "pressure_value"
    elif re.match(r"^(?:REV(?:ISION)?\.?\s*[:=-]?\s*)[A-Z0-9]+$", normalized):
        category = "revision"
    elif re.search(r"\b(?:P&ID|PIPING AND INSTRUMENTATION|DRAWING TITLE)\b", normalized):
        category = "drawing_title"
    return normalized, category, tags
