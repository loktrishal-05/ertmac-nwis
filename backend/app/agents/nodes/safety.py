"""The safety & incident agent (Phase 4D). Emits S7 (a proposal for human
review) or S5 (refusal) -- never S1/S3, and never an output that reads as
authorisation to act. Also handles `combined_safety_maintenance` (D-004):
the same node, additionally pulling in read-only maintenance/sensor evidence
for any equipment tag detected deterministically in the query text.

The safety property this sub-phase enforces in code: no output ever reads as
authorisation to act. Two independent layers: `safety_language.py`'s
deterministic forbidden-construction scan (wrapped into the bounded
reject-or-regenerate loop below), and `_harden_action_recommendation()`,
which overrides whatever `approval_status`/`human_approval_required` the
model proposed -- this system never self-approves an action, regardless of
what the model says, and every non-informational action always carries
`human_approval_required=True` on the record."""
import json

from app.agents.enforcement import EnforcementFailure, enforce_citations_and_authorization_language, operational_action_text, refuse, unknown_reference_ids
from app.agents.prompts.safety import SAFETY_SYSTEM_PROMPT, build_safety_user_message, format_evidence_block, format_evidence_ref
from app.agents.registry import invoke_tool
from app.schemas.agent_outputs import ActionRecommendation
from app.services.model_gateway import ChatMessage, StructuredOutputError, get_model_gateway
from app.services.sparse import identifiers as extract_identifiers

SUB_PHASE = "4D"

# Most cautious first: a dominant action_class is reported at the state level
# as the single most severe class among this turn's proposed actions.
_ACTION_CLASS_SEVERITY = ("shutdown", "isolation", "process_change", "inspection", "informational")
_MAX_COMBINED_TAGS = 3


def _row_block(evidence_id: str, locator: str, row: dict) -> str:
    payload = {key: value for key, value in row.items() if key != "evidence_id"}
    return format_evidence_block(evidence_id, locator, json.dumps(payload, default=str))


def _gather_evidence(state, session):
    """Returns (evidence_refs, evidence_blocks, warnings). retrieve_documents
    always runs; combined_safety_maintenance additionally pulls read-only
    maintenance/sensor evidence for each equipment tag the query names,
    deterministically extracted (app.services.sparse.identifiers), never
    guessed by the model."""
    query = state["query"]
    payload, refs = invoke_tool("retrieve_documents", session, {"query": query})
    warnings = list(payload.get("warnings", []))
    evidence = list(refs)
    blocks = [format_evidence_ref(ref) for ref in refs]

    if state.get("route") == "combined_safety_maintenance":
        tags = extract_identifiers(query).get("equipment_tags", [])[:_MAX_COMBINED_TAGS]
        for tag in tags:
            m_payload, m_refs = invoke_tool("get_maintenance_history", session, {"equipment_tag": tag, "limit": 20})
            evidence += m_refs
            warnings += m_payload.get("warnings", [])
            for row, ref in zip(m_payload.get("records", []), m_refs):
                blocks.append(_row_block(ref.evidence_id, f"maintenance history for {tag}", row))

            s_payload, s_refs = invoke_tool("get_latest_reading", session, {"equipment_tag": tag})
            evidence += s_refs
            for row, ref in zip(s_payload.get("readings", []), s_refs):
                blocks.append(_row_block(ref.evidence_id, f"latest sensor reading for {tag}", row))

    return evidence, blocks, warnings


def _dominant_action_class(recommendation: ActionRecommendation) -> str | None:
    present = {action.action_class for action in recommendation.proposed_actions}
    for action_class in _ACTION_CLASS_SEVERITY:
        if action_class in present:
            return action_class
    return None


def _harden_action_recommendation(recommendation: ActionRecommendation) -> ActionRecommendation:
    """This system never self-approves: any `approval_status="approved"` the
    model emitted is downgraded to "required" unconditionally, and every
    non-informational action forces `human_approval_required=True` at the
    top level, regardless of what the model set. Access-scope metadata (if
    any future field carries it) is never read as authorisation here --
    only `action_class`/`evidence_basis` inform this."""
    any_non_informational = False
    hardened_actions = []
    for action in recommendation.proposed_actions:
        approval_status = action.approval_status
        if approval_status == "approved":
            approval_status = "required"
        action_class = action.action_class
        if action_class == "informational" and operational_action_text(action.action):
            action_class = "shutdown" if any(word in action.action.lower() for word in ("start", "stop", "restart", "shut", "isolate", "bypass", "override")) else "process_change"
        if action_class != "informational":
            any_non_informational = True
            if approval_status == "not_required":
                approval_status = "required"
        hardened_actions.append(action.model_copy(update={"approval_status": approval_status, "action_class": action_class}))
    return recommendation.model_copy(update={
        "proposed_actions": hardened_actions,
        "human_approval_required": recommendation.human_approval_required or any_non_informational,
    })


def safety_node(state, gateway=None, session=None) -> dict:
    gateway = gateway or get_model_gateway()
    evidence, blocks, warnings = _gather_evidence(state, session)

    if not evidence:
        refusal = refuse(
            status="insufficient_evidence",
            reason="No SOP, incident, or equipment evidence was found for this safety-relevant request.",
            missing_evidence=[state["query"]],
            safe_next_step="Escalate immediately to a supervisor or the site's emergency response process; "
                           "this system found no citable procedure or equipment record to base guidance on.",
        )
        return {"agent_result": {"schema": "S5", "output": refusal.model_dump(mode="json")},
                "evidence": evidence, "warnings": warnings}

    def _generate(retry_note: str | None) -> ActionRecommendation:
        messages = [
            ChatMessage(role="system", content=SAFETY_SYSTEM_PROMPT),
            ChatMessage(role="user", content=build_safety_user_message(state["query"], blocks)),
        ]
        if retry_note:
            messages.append(ChatMessage(role="user", content=retry_note))
        try:
            result = gateway.generate_structured(messages=messages, schema=ActionRecommendation, think=False)
        except StructuredOutputError as error:
            raise EnforcementFailure(refuse(
                status="refused",
                reason="The model did not produce a schema-valid safety recommendation from the gathered evidence.",
                safe_next_step="Retry the request, or escalate directly to a supervisor if this is urgent.",
            )) from error
        return result.value

    def _language_text(recommendation: ActionRecommendation) -> str:
        return " ".join([recommendation.summary, *recommendation.evidence_basis, *recommendation.warnings,
                          *(citation.claim for citation in recommendation.citations),
                          *(action.action for action in recommendation.proposed_actions)])

    try:
        recommendation = enforce_citations_and_authorization_language(
            generate=_generate, extract_citations=lambda value: value.citations,
            extract_language_text=_language_text, available=evidence, require_citations=True,
        )
    except EnforcementFailure as failure:
        return {"agent_result": {"schema": "S5", "output": failure.refusal.model_dump(mode="json")},
                "evidence": evidence, "warnings": warnings}

    recommendation = _harden_action_recommendation(recommendation)
    bad_refs = unknown_reference_ids(recommendation.evidence_basis, evidence)
    if bad_refs:
        refusal = refuse(status="insufficient_evidence",
                         reason="The generated safety recommendation referenced evidence not supplied for this turn.",
                         missing_evidence=bad_refs,
                         safe_next_step="Retry using only the evidence supplied for this request.")
        return {"agent_result": {"schema": "S5", "output": refusal.model_dump(mode="json")},
                "evidence": evidence, "warnings": warnings}
    return {
        "agent_result": {"schema": "S7", "output": recommendation.model_dump(mode="json")},
        "evidence": evidence, "warnings": warnings,
        "human_approval_required": recommendation.human_approval_required,
        "action_class": _dominant_action_class(recommendation),
    }
