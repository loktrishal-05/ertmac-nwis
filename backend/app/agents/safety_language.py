"""Supplemental authorization-language heuristic; never an approval boundary."""
import re

_PATTERNS = (
    r"you(?:'re| are)\s+(?:now\s+|hereby\s+)?cleared\s+(?:to|for)",
    r"permission\s+(?:is|has been)\s+(?:hereby\s+)?granted",
    r"(?:you may now|go ahead and|proceed with|authorize|authorise)\b",
    r"you(?:'re| are)\s+authori[sz](?:ed|ation)\b",
    r"permit\s+(?:is|has been)\s+(?:issued|approved)",
    r"(?:consider|mark)\s+(?:it|this|the action)\s+(?:approved|authori[sz]ed|granted)",
    r"\b(?:start|stop|restart|open|close|isolate|bypass|override|suppress|defeat|energize|de-energize)\s+(?:the\s+)?[A-Z0-9][A-Z0-9_-]{1,}",
    r"\b(?:bring|take|return)\s+[A-Z0-9][A-Z0-9_-]{1,}.*\b(?:online|offline|to service)\b",
    r"\bremove\s+(?:the\s+)?(?:trip|alarm|interlock)\b",
    r"\b(?:already|supervisor)\s+approved\b.{0,40}\bproceed\b",
    r"\bsupervisor\s+approved\b",
    r"\bmark\s+(?:this\s+)?action\s+approved\b",
    r"\bexecute\s+(?:the\s+)?(?:isolation|shutdown|restart)\b",
    r"\b(?:if|when)\b.{0,100}\b(?:start|stop|restart|open|close|isolate|bypass|override|shut down)\b",
)
_FORBIDDEN_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in _PATTERNS]
_ACTION_WORD = re.compile(r"\b(?:start|stop|restart|open|close|isolate|bypass|override|suppress|defeat|energize|de-energize|shut\s*down)\b", re.IGNORECASE)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def strip_quoted_spans(text: str) -> str:
    """Removes single/double-quoted substrings so a pattern scan never fires on
    a quotation of the forbidden phrase (e.g. a document excerpt that mentions
    it). Reused by app.services.preflight for the same reason (context
    matters: quoting something is not saying it)."""
    return re.sub(r"(['\"]).*?\1", " ", text)


def _candidate_sentences(text: str) -> list[str]:
    text = strip_quoted_spans(text)
    sentences = re.split(r"(?<=[.!?])\s+|[;\n]+", text)
    excluded = re.compile(
        r"\b(?:explain|describe|summari[sz]e|the\s+(?:sop|phrase|instruction)\s+says|"
        r"what\s+could\s+happen|consequences\s+of|do\s+not|don't|never|must\s+not|"
        r"not\s+authorized|not\s+authorised|authorized\s+to\s+request|authorised\s+to\s+request|"
        r"no\s+(?:permit|approval)\s+is?\s+approved|if\s+someone\s+said|would\s+be)\b", re.IGNORECASE,
    )
    return [s for s in sentences if s and not excluded.search(s)]


def find_authorization_language(text: str) -> list[str]:
    normalized = _normalized(text)
    if not normalized:
        return []
    candidates = _candidate_sentences(normalized)
    violations = []
    for index, pattern in enumerate(_FORBIDDEN_PATTERNS):
        if any(pattern.search(sentence) for sentence in candidates):
            violations.append(("direct operational action: " if index >= 6 else "") + pattern.pattern)
    if any(_ACTION_WORD.search(sentence) for sentence in candidates):
        violations.append("direct operational action language")
    return violations


def contains_authorization_language(text: str) -> bool:
    return bool(find_authorization_language(text))
