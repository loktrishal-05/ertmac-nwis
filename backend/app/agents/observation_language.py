"""The asymmetric observation/hypothesis word-ban validator (Phase 4E).

Phase 3C's own `test_no_observation_ever_names_a_diagnosis`
(backend/tests/test_structured.py) established a flat ban on six words
("bearing", "failure", "damage", "cavitation", "diagnos", "impeller") in
factual sensor observations -- reused here verbatim, not re-derived, since
it is the existing precedent for exactly this boundary. 4E generalizes it to
the asymmetric form the brief requires: forbidden in `observations[]`
(measured fact only), permitted in `hypotheses[]` (interpretation is exactly
where a failure mode belongs). A flat ban on both would make the maintenance
agent unable to ever propose a diagnostic hypothesis; no ban anywhere would
lose the distinction the product is built on -- see
docs/phase4-decisions.md."""
import re

DIAGNOSTIC_WORDS = ("bearing", "failure", "damage", "cavitation", "diagnos", "impeller")
_PATTERN = re.compile("|".join(re.escape(word) for word in DIAGNOSTIC_WORDS), re.IGNORECASE)
_UNSUPPORTED = re.compile(r"\b(?:certainly|definitely|confirmed|is|was|because|due to|caused by)\b.{0,80}\b(?:leak|misalign|failure|fault|damage|blocked|clogged)\b", re.IGNORECASE)
_FACTUAL_MARKER = re.compile(r"\b(?:read(?:ing)?|measur(?:ed|ement)|observ(?:ed|ation)|recorded|detected|inspected|value|trend|increased|decreased|stable|stale|quality|sample|at\s+\d{1,2}:\d{2}|\d+(?:\.\d+)?)\b", re.IGNORECASE)


def find_diagnostic_language(text: str) -> list[str]:
    if not text:
        return []
    return sorted({match.group(0).lower() for match in _PATTERN.finditer(text)})


def contains_diagnostic_language(text: str) -> bool:
    return bool(find_diagnostic_language(text))


def find_observation_language_violations(text: str) -> list[str]:
    """Reject diagnoses/causal certainty and prose without an evidence marker."""
    violations = find_diagnostic_language(text)
    if _UNSUPPORTED.search(text or ""):
        violations.append("unsupported diagnostic or causal assertion")
    if text and not _FACTUAL_MARKER.search(text):
        violations.append("observation lacks a measurement or recorded-event marker")
    return sorted(set(violations))
