"""The deterministic citation validator. A pure function: no database access,
no model call. It REPORTS; it never raises and never edits an answer.

Built and tested exhaustively here, in Phase 4B, while there is no agent
output yet to rationalise a broken validator against. Enforcement — rejecting
or repairing an answer that cites something unknown — is Phase 4C."""
from typing import Sequence

from pydantic import BaseModel, ConfigDict

from app.agents.evidence import EvidenceRef


class CitationValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valid: bool
    unknown_ids: list[str]
    uncited_evidence_ids: list[str]
    cited_count: int
    available_count: int


def validate_citations(*, emitted: Sequence[str], available: Sequence[EvidenceRef], citations=None,
                       require_citations: bool = False) -> CitationValidationResult:
    available_ids = {ref.evidence_id for ref in available}
    emitted_set = set(emitted)
    unknown_ids = sorted(emitted_set - available_ids)
    available_by_id = {ref.evidence_id: ref for ref in available}
    for citation in citations or []:
        ref = available_by_id.get(citation.evidence_id)
        if ref is not None and citation.locator != ref.locator:
            unknown_ids.append(f"{citation.evidence_id}:locator")
    if require_citations and not emitted_set:
        unknown_ids.append("(citation required)")
    uncited_ids = sorted(available_ids - emitted_set)
    return CitationValidationResult(
        valid=not unknown_ids,
        unknown_ids=unknown_ids,
        uncited_evidence_ids=uncited_ids,
        cited_count=len(emitted_set),
        available_count=len(available_ids),
    )
