"""The knowledge & multimodal retrieval agent (Phase 4C). Emits S1 (grounded
answer), S3 (OCR-derived equipment-tag identification) or S5 (refusal) --
never invents an evidence_id, and never labels an equipment tag "verified"
on OCR confidence alone.

Evidence sufficiency is decided in CODE (_assess_evidence), never left to the
model: Phase 3B2 proved dense/hybrid retrieval returns unrelated neighbours
for a nonexistent identifier (ZZQ-99999), so an empty result set is not the
only failure signal. See docs/phase4-autonomous-continuation.md section 5 and
docs/phase4-decisions.md D-006/D-007."""
from sqlalchemy import select

from app.agents.enforcement import CitationEnforcementFailure, enforce_citations, refuse
from app.agents.prompts.knowledge import (
    KNOWLEDGE_SYSTEM_PROMPT,
    build_knowledge_user_message,
    format_evidence_block,
    format_evidence_ref,
)
from app.agents.registry import invoke_tool
from app.core.config import settings
from app.db.models.equipment import Equipment
from app.schemas.agent_outputs import EquipmentTag, EquipmentTags, GroundedAnswer
from app.services.equipment_tags import normalize_equipment_tag
from app.services.model_gateway import ChatMessage, StructuredOutputError, get_model_gateway

SUB_PHASE = "4C"
_IDENTIFIER_MISS_MARKER = "No lexical evidence matched"


def _assess_evidence(payload: dict) -> tuple[bool, str | None]:
    """Combines two independent signals in code: an empty/below-floor top
    score, and the retriever's own identifier-miss warning. Either alone is
    sufficient to refuse -- deliberately, not just when both agree. Phase 3B2
    (docs/phase3b2-validation.md) measured dense/hybrid retrieval returning
    unrelated neighbours, sometimes with an unremarkable score, for a
    nonexistent identifier; trusting the score alone in that situation would
    silently answer from a neighbour. Per the autonomy charter's "choose the
    more conservative option" rule (docs/phase4-decisions.md D-007), an
    identifier miss refuses regardless of what any neighbour scored."""
    results = payload.get("results", [])
    identifier_miss = any(_IDENTIFIER_MISS_MARKER in warning for warning in payload.get("warnings", []))
    if not results:
        return False, "No evidence was retrieved for this query."
    top_score = max(result["score"] for result in results)
    below_floor = top_score < settings.knowledge_relevance_floor
    if below_floor or identifier_miss:
        detail = " No lexical evidence matched a technical identifier in the query." if identifier_miss else ""
        return False, (
            f"The best available evidence (score {top_score:.3f}) did not reach the configured relevance "
            f"floor ({settings.knowledge_relevance_floor}).{detail}"
        )
    return True, None


def _registry_confirms(session, raw_text: str) -> bool:
    if session is None or not raw_text:
        return False
    normalized = normalize_equipment_tag(raw_text.strip())
    if not normalized:
        return False
    return session.scalar(select(Equipment.id).where(Equipment.equipment_tag == normalized)) is not None


def _equipment_tags_from_ocr(refs, session) -> EquipmentTags:
    tags = []
    for ref in refs:
        # Status is computed here, deterministically, from the registry lookup and
        # the OCR pipeline's own status -- never from OCR confidence, however high.
        normalized = normalize_equipment_tag(ref.quote.strip()) if ref.quote else None
        if normalized and _registry_confirms(session, normalized):
            status = "verified"
        else:
            status = ref.ocr_status or "unverified"
        tags.append(EquipmentTag(
            raw_text=ref.quote, normalized_tag=normalized, equipment_type=None,
            evidence_id=ref.evidence_id, confidence=ref.ocr_confidence or 0.0, status=status,
        ))
    warnings = [] if tags else ["No OCR-derived equipment-tag evidence was present in this turn's results."]
    return EquipmentTags(tags=tags, warnings=warnings)


def knowledge_node(state, gateway=None, session=None) -> dict:
    gateway = gateway or get_model_gateway()
    payload, refs = invoke_tool("retrieve_documents", session, {"query": state["query"]})
    warnings = list(payload.get("warnings", []))

    sufficient, insufficiency_reason = _assess_evidence(payload)
    if not sufficient:
        refusal = refuse(
            status="insufficient_evidence", reason=insufficiency_reason,
            missing_evidence=[state["query"]],
            safe_next_step="Confirm the identifier or document exists, or rephrase the question with a "
                           "specific, known equipment tag or document reference before asking again.",
        )
        return {
            "agent_result": {"schema": "S5", "output": refusal.model_dump(mode="json")},
            "evidence": refs, "warnings": warnings,
        }

    ocr_refs = [ref for ref in refs if getattr(ref, "kind", None) == "document_chunk" and ref.ocr_derived]
    if ocr_refs:
        tags = _equipment_tags_from_ocr(ocr_refs, session)
        return {
            "agent_result": {"schema": "S3", "output": tags.model_dump(mode="json")},
            "evidence": refs, "warnings": warnings,
        }

    blocks = [format_evidence_ref(ref) for ref in refs]

    def _generate(retry_note: str | None) -> GroundedAnswer:
        messages = [
            ChatMessage(role="system", content=KNOWLEDGE_SYSTEM_PROMPT),
            ChatMessage(role="user", content=build_knowledge_user_message(state["query"], blocks)),
        ]
        if retry_note:
            messages.append(ChatMessage(role="user", content=retry_note))
        try:
            result = gateway.generate_structured(messages=messages, schema=GroundedAnswer, think=False)
        except StructuredOutputError as error:
            raise CitationEnforcementFailure(refuse(
                status="insufficient_evidence",
                reason="The model did not produce a schema-valid grounded answer from the gathered evidence.",
                safe_next_step="Retry the question; if this persists, the model runtime may need attention.",
            )) from error
        return result.value

    try:
        answer = enforce_citations(generate=_generate, extract_citations=lambda value: value.citations,
                                    available=refs, require_citations=True)
    except CitationEnforcementFailure as failure:
        return {
            "agent_result": {"schema": "S5", "output": failure.refusal.model_dump(mode="json")},
            "evidence": refs, "warnings": warnings,
        }

    return {
        "agent_result": {"schema": "S1", "output": answer.model_dump(mode="json")},
        "evidence": refs, "warnings": warnings,
    }
