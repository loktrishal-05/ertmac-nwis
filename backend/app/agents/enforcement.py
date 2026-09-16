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
catch it and return the prior (invalid) result."""
from typing import Callable, Sequence, TypeVar

from pydantic import BaseModel

from app.agents.citations import validate_citations
from app.agents.evidence import EvidenceRef
from app.schemas.agent_outputs import Citation, Refusal

T = TypeVar("T", bound=BaseModel)


def refuse(
    *, status: str, reason: str, safe_next_step: str,
    missing_evidence: Sequence[str] | None = None, citations: Sequence[Citation] | None = None,
) -> Refusal:
    return Refusal(
        status=status, reason=reason, safe_next_step=safe_next_step,
        missing_evidence=list(missing_evidence or []), citations=list(citations or []),
    )


class CitationEnforcementFailure(Exception):
    """Carries a ready-to-return S5 Refusal. The node that raises this must
    return the refusal, never the invalid structured result that triggered it."""

    def __init__(self, refusal: Refusal):
        super().__init__(refusal.reason)
        self.refusal = refusal


def enforce_citations(
    *, generate: Callable[[str | None], T], extract_citations: Callable[[T], Sequence[Citation]],
    available: Sequence[EvidenceRef], max_attempts: int = 2,
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
        emitted = [c.evidence_id for c in extract_citations(result)]
        check = validate_citations(emitted=emitted, available=available)
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
