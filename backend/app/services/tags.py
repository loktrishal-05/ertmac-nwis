"""Deterministic configurable identifier patterns, not ML detection."""
import re

DEFAULT_PATTERNS = {
    "equipment_tags": r"(?<![A-Z0-9-])(?:P|V|E|C|T|R|K|M)-\d{2,5}[A-Z]?(?![A-Z0-9-])",
    "instrument_tags": r"(?<![A-Z0-9-])(?:FV|TT|PT|FT|LT|LV|PV|TV|FIC|PIC|TIC|LIC|PSV)-\d{2,5}[A-Z]?(?![A-Z0-9-])",
    "line_numbers": r'(?<![A-Z0-9-])\d{1,2}(?:/\d)?["\u2033]-[A-Z]{1,5}-\d{2,6}(?:-[A-Z0-9]+)*(?![A-Z0-9-])',
}


def extract_tags(text: str, patterns: dict[str, str] | None = None) -> dict[str, list[str]]:
    return {
        key: sorted(set(re.findall(pattern, text.upper())))
        for key, pattern in (patterns or DEFAULT_PATTERNS).items()
    }
