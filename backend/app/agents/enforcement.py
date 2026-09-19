"""Shared enforcement helpers used by every specialist agent node in 4C-4F.

refuse() builds the S5 Refusal body directly in Python -- never through the
model gateway. A refusal's reason, missing evidence and safe next step are
already known to the calling code from tool results and validator output;
asking the model to phrase them risks it inventing a plausible-sounding but
false justification for a security-relevant outcome, which is worse than a
terse but accurate one. See docs/phase4-decisions.md D-006.

enforce_citations() wraps the Phase 4B citation validator (app.agents.citations)
into the actual reject-or-regenerate control flow 4B stopped short of: one
bounded regeneration attempt carrying the validator's own error message, then
a structural refusal. It never strips a bad citation and ships the answer --
callers must propagate CitationEnforcementFailure into an S5 response, never
catch it and return the prior (invalid) result.

enforce_citations_and_authorization_language() is the 4D/4F variant: the same
reject-or-regenerate shape, but checking both citation validity AND the
authorisation-language validator (app.agents.safety_language) in a single
bounded regeneration, since the 4D brief requires 4F to reuse 4D's validator
directly rather than reimplement it. See docs/phase4-decisions.md D-006.

enforce_citations_and_diagnostic_language() is the 4E variant, for the S4
maintenance-assessment path specifically: free-text `observations` must never
name a failure mode (app.agents.observation_language's word ban) while
`hypotheses` remain free to. Only used on the S4 (general assessment) path --
4E's S6 (threshold-loop) path never lets the model author `observations` at
all, so there is nothing there for this function to check."""
import re
from typing import Callable, Sequence, TypeVar

from pydantic import BaseModel

from app.agents.citations import validate_citations
from app.agents.evidence import EvidenceRef
from app.agents.observation_language import find_diagnostic_language, find_observation_language_violations
from app.agents.safety_language import find_authorization_language
from app.schemas.agent_outputs import Citation, Refusal

_OPERATIONAL_ACTION = re.compile(
    r"\b(?:start|stop|restart|shut\s*down|open|close|isolate|bypass|override|suppress|defeat|"
    r"energize|de-energize|bring\s+[^.?!]{0,40}\s+online|take\s+[^.?!]{0,40}\s+offline|"
    r"return\s+[^.?!]{0,40}\s+to\s+service)\b", re.IGNORECASE,
)


def operational_action_text(text: str) -> bool:
    """Deterministic advisory classification; never an approval decision."""
    return bool(_OPERATIONAL_ACTION.search(text or ""))


def unknown_reference_ids(ids: Sequence[str], available: Sequence[EvidenceRef]) -> list[str]:
    allowed = {ref.evidence_id for ref in available}
    return sorted({item for item in ids if item not in allowed})

T = TypeVar("T", bound=BaseModel)


def refuse(
    *, status: str, reason: str, safe_next_step: str,
    missing_evidence: Sequence[str] | None = None, citations: Sequence[Citation] | None = None,
) -> Refusal:
    return Refusal(
        status=status, reason=reason, safe_next_step=safe_next_step,
        missing_evidence=list(missing_evidence or []), citations=list(citations or []),
    )


class EnforcementFailure(Exception):
    """Carries a ready-to-return S5 Refusal. The node that raises this (or a
    subclass of it) must return the refusal, never the invalid structured
    result that triggered it."""

    def __init__(self, refusal: Refusal):
        super().__init__(refusal.reason)
        self.refusal = refusal


class CitationEnforcementFailure(EnforcementFailure):
    """Raised by enforce_citations() specifically -- a citation-only failure."""


def enforce_citations(
    *, generate: Callable[[str | None], T], extract_citations: Callable[[T], Sequence[Citation]],
    available: Sequence[EvidenceRef], max_attempts: int = 2, require_citations: bool = False,
) -> T:
    """generate(None) is the first attempt. On a citation failure, generate is
    called once more with a retry_note carrying the validator's own unknown-id
    list (the "one bounded regeneration attempt" the 4C brief requires). If
    citations are still invalid after max_attempts, raises
    CitationEnforcementFailure with the S5 body already built."""
    retry_note = None
    last_check = None
    for _ in range(max_attempts):
        result = generate(retry_note)
        citations = list(extract_citations(result))
        emitted = [c.evidence_id for c in citations]
        check = validate_citations(emitted=emitted, available=available, citations=citations,
                                   require_citations=require_citations)
        if check.valid:
            return result
        last_check = check
        retry_note = (
            f"The previous response cited evidence_id value(s) {check.unknown_ids} that do not appear in the "
            "evidence gathered for this turn. Cite only evidence_id values that were supplied to you, or omit "
            "the unsupported claim."
        )
    raise CitationEnforcementFailure(refuse(
        status="insufficient_evidence",
        reason=(
            "The generated answer cited evidence_id value(s) not present in this turn's gathered evidence "
            f"({last_check.unknown_ids}), even after one bounded regeneration attempt."
        ),
        missing_evidence=last_check.unknown_ids,
        safe_next_step="Rephrase the question or narrow it to a specific document, region, or equipment tag.",
    ))


def enforce_citations_and_authorization_language(
    *, generate: Callable[[str | None], T], extract_citations: Callable[[T], Sequence[Citation]],
    extract_language_text: Callable[[T], str], available: Sequence[EvidenceRef], max_attempts: int = 2,
    require_citations: bool = False,
) -> T:
    """Used by 4D (safety & incident) and 4F (process optimization): the same
    bounded reject-or-regenerate shape as enforce_citations(), but a single
    regeneration attempt must fix BOTH a citation problem and an
    authorisation-language problem if both are present -- never two separate
    regeneration budgets stacked on top of each other."""
    retry_note = None
    last_unknown_ids: list[str] = []
    last_violations: list[str] = []
    for _ in range(max_attempts):
        result = generate(retry_note)
        citations = list(extract_citations(result))
        emitted = [c.evidence_id for c in citations]
        citation_check = validate_citations(emitted=emitted, available=available, citations=citations,
                                            require_citations=require_citations)
        # Direct action wording is retained as an advisory signal for policy
        # classification, but only explicit clearance/approval language blocks
        # an output here. The heuristic is never the approval authority.
        violations = [item for item in find_authorization_language(extract_language_text(result))
                      if not item.startswith("direct operational action") and item != "direct operational action language"]
        if citation_check.valid and not violations:
            return result
        last_unknown_ids, last_violations = citation_check.unknown_ids, violations
        notes = []
        if not citation_check.valid:
            notes.append(f"cited evidence_id value(s) not gathered this turn: {citation_check.unknown_ids}")
        if violations:
            notes.append(
                "used language that reads as granting authorisation or clearance to act "
                f"(matched: {violations}); restate any procedure reference as a citation to what the "
                "procedure says, never as permission granted by you"
            )
        retry_note = "The previous response is invalid: " + "; and ".join(notes) + ". Respond again with only the corrected JSON object."
    # The refusal's own `reason` is user-facing (returned in agent_result), so it
    # never repeats the model's rejected wording -- only that a rejection happened
    # and the pattern-match count, never the raw regex source or the flagged text.
    reason_parts = []
    if last_unknown_ids:
        reason_parts.append(f"cited {len(last_unknown_ids)} unknown evidence_id value(s)")
    if last_violations:
        reason_parts.append(f"used authorisation-implying language ({len(last_violations)} pattern match(es))")
    raise EnforcementFailure(refuse(
        status="refused" if last_violations else "insufficient_evidence",
        reason="The generated recommendation " + " and ".join(reason_parts) + ", even after one bounded regeneration attempt.",
        missing_evidence=last_unknown_ids,
        safe_next_step="A qualified, authorised person must independently confirm and grant any permit, LOTO, "
                       "or isolation clearance; this system never grants one.",
    ))


def enforce_citations_and_diagnostic_language(
    *, generate: Callable[[str | None], T], extract_citations: Callable[[T], Sequence[Citation]],
    extract_observation_text: Callable[[T], str], available: Sequence[EvidenceRef], max_attempts: int = 2,
    require_citations: bool = False,
) -> T:
    """4E's S4 variant: `observations` (free text) must never name a failure
    mode; `hypotheses` are never checked here (the ban is asymmetric by
    design -- see app.agents.observation_language)."""
    retry_note = None
    last_unknown_ids: list[str] = []
    last_violations: list[str] = []
    for _ in range(max_attempts):
        result = generate(retry_note)
        citations = list(extract_citations(result))
        emitted = [c.evidence_id for c in citations]
        citation_check = validate_citations(emitted=emitted, available=available, citations=citations,
                                            require_citations=require_citations)
        violations = find_observation_language_violations(extract_observation_text(result))
        if citation_check.valid and not violations:
            return result
        last_unknown_ids, last_violations = citation_check.unknown_ids, violations
        notes = []
        if not citation_check.valid:
            notes.append(f"cited evidence_id value(s) not gathered this turn: {citation_check.unknown_ids}")
        if violations:
            notes.append(
                f"used a diagnostic/failure-mode word {violations} inside `observations`, which must stay "
                "strictly factual (measured values, trends, or quality flags only) -- move any diagnostic "
                "interpretation into `hypotheses` instead, with its own supporting_evidence or "
                "contradicting_evidence"
            )
        retry_note = "The previous response is invalid: " + "; and ".join(notes) + ". Respond again with only the corrected JSON object."
    reason_parts = []
    if last_unknown_ids:
        reason_parts.append(f"cited {len(last_unknown_ids)} unknown evidence_id value(s)")
    if last_violations:
        reason_parts.append(f"named a failure mode inside `observations` ({len(last_violations)} word match(es))")
    raise EnforcementFailure(refuse(
        status="insufficient_evidence",
        reason="The generated assessment " + " and ".join(reason_parts) + ", even after one bounded regeneration attempt.",
        missing_evidence=last_unknown_ids,
        safe_next_step="Rephrase the question or narrow it to a specific equipment tag or time range.",
    ))
