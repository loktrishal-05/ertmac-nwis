"""The process optimization agent (Phase 4F). Emits S7 (process change
proposals for human review) or S5 (refusal).

The safety property this sub-phase enforces in code: every set-point or valve
suggestion is a proposal for human review, never an instruction.

Two implementations of this principle:
1. The authorisation-language validator (reused from 4D, app.agents.safety_language)
   ensures the output never reads as an instruction or directive.
2. The _harden_process_change_recommendation() function (modelled on 4D's
   _harden_action_recommendation) forces every proposed action's action_class
   to "process_change" and human_approval_required to true, regardless of
   what the model proposed.

Confounder acknowledgement (surface competing explanations for correlated
trends, not hiding one interpretation behind another) is enforced at the
prompt level via OPTIMIZATION_SYSTEM_PROMPT, validated by a fixture test
that passes a trend where two variables move together and asserts that both
are mentioned in the response.

Evidence gathering uses compute_sensor_features (which returns pre-computed
trend metrics like slope and percentage_change from Phase 3C), maintenance
history, and SOP documentation. The model proposes and phrases improvements;
arithmetic is never left to the model."""
import json
from datetime import datetime, timedelta, timezone

from app.agents.enforcement import (
    EnforcementFailure,
    enforce_citations_and_authorization_language,
    refuse,
    unknown_reference_ids,
)
from app.agents.prompts.optimization import (
    OPTIMIZATION_SYSTEM_PROMPT,
    build_optimization_user_message,
)
from app.agents.prompts.shared import format_evidence_block, format_evidence_ref
from app.agents.registry import invoke_tool
from app.schemas.agent_outputs import ActionRecommendation, Citation, ProposedAction
from app.services.model_gateway import ChatMessage, StructuredOutputError, get_model_gateway
from app.services.sparse import identifiers as extract_identifiers

SUB_PHASE = "4F"

_TREND_WINDOW_DAYS = 30
_MAX_HISTORY_ROWS = 20
_MAX_SENSOR_FEATURES = 6


def _row_block(evidence_id: str, locator: str, row: dict) -> str:
    payload = {key: value for key, value in row.items() if key != "evidence_id"}
    return format_evidence_block(evidence_id, locator, json.dumps(payload, default=str))


def _harden_process_change_recommendation(recommendation: ActionRecommendation) -> ActionRecommendation:
    """This system never lets the model dictate approval: every proposed action
    is re-written with action_class='process_change' and approval_status='required',
    regardless of what the model proposed. The top-level human_approval_required
    is forced to true. Reuses the pattern from 4D's _harden_action_recommendation."""
    hardened_actions = []
    for action in recommendation.proposed_actions:
        hardened_actions.append(action.model_copy(update={
            "action_class": "process_change",
            "approval_status": "required",
        }))
    return recommendation.model_copy(update={
        "proposed_actions": hardened_actions,
        "human_approval_required": True,
    })


def optimization_node(state, gateway=None, session=None) -> dict:
    gateway = gateway or get_model_gateway()
    query = state["query"]
    tags = extract_identifiers(query).get("equipment_tags", [])

    if not tags:
        refusal = refuse(
            status="insufficient_evidence",
            reason="No equipment tag was found in this request.",
            missing_evidence=[query],
            safe_next_step="Include the specific equipment tag (e.g. P-204) and ask again.",
        )
        return {"agent_result": {"schema": "S5", "output": refusal.model_dump(mode="json")},
                "evidence": [], "warnings": []}

    tag = tags[0]
    evidence = []
    warnings = []
    blocks = []

    # Retrieve operational SOP/documentation for context.
    doc_payload, doc_refs = invoke_tool("retrieve_documents", session, {"query": query})
    warnings += doc_payload.get("warnings", [])
    evidence += doc_refs
    for ref in doc_refs:
        blocks.append(format_evidence_ref(ref))

    # Retrieve latest sensor reading to identify the sensor_tag for trend analysis.
    latest_payload, latest_refs = invoke_tool("get_latest_reading", session, {"equipment_tag": tag})
    latest_readings = latest_payload.get("readings", [])

    # Retrieve sensor trends for the equipment tag using compute_sensor_features
    # (pre-computed slope, percentage_change, etc. from Phase 3C, no thresholds).
    evidence += latest_refs
    for reading in latest_readings[:_MAX_SENSOR_FEATURES]:
        sensor_tag = reading.get("sensor_tag")
        if not sensor_tag:
            continue
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=_TREND_WINDOW_DAYS)
        trend_payload, trend_refs = invoke_tool("compute_sensor_features", session, {
            "equipment_tag": tag, "sensor_tag": sensor_tag,
            "start": start.isoformat(), "end": end.isoformat(),
        })
        warnings += trend_payload.get("warnings", [])
        evidence += trend_refs
        if trend_refs:
            # Forward the deterministic feature summary itself. The model may
            # explain it, but it must not recompute authoritative numbers.
            feature_payload = {
                "sensor_tag": sensor_tag,
                "measurement": trend_payload.get("measurement"),
                "features": trend_payload.get("features", {}),
                "observations": trend_payload.get("observations", [])[:20],
            }
            blocks.append(format_evidence_block(
                trend_refs[0].evidence_id, trend_refs[0].locator,
                json.dumps(feature_payload, default=str),
            ))

    # Retrieve maintenance history for operational context.
    hist_payload, hist_refs = invoke_tool(
        "get_maintenance_history", session, {"equipment_tag": tag, "limit": _MAX_HISTORY_ROWS},
    )
    warnings += hist_payload.get("warnings", [])
    evidence += hist_refs
    history_blocks = [
        _row_block(ref.evidence_id, f"maintenance history for {tag}", row)
        for row, ref in zip(hist_payload.get("records", []), hist_refs)
    ]
    blocks.extend(history_blocks)

    if not evidence:
        refusal = refuse(
            status="insufficient_evidence",
            reason=f"No operational documentation, sensor data, or maintenance history was found for {tag}.",
            missing_evidence=[tag],
            safe_next_step="Confirm the equipment tag is correct, or ask again once records exist for it.",
        )
        return {"agent_result": {"schema": "S5", "output": refusal.model_dump(mode="json")},
                "evidence": evidence, "warnings": warnings}

    def _generate(retry_note: str | None) -> ActionRecommendation:
        messages = [
            ChatMessage(role="system", content=OPTIMIZATION_SYSTEM_PROMPT),
            ChatMessage(role="user", content=build_optimization_user_message(query, tag, blocks)),
        ]
        if retry_note:
            messages.append(ChatMessage(role="user", content=retry_note))
        try:
            result = gateway.generate_structured(messages=messages, schema=ActionRecommendation, think=False)
        except StructuredOutputError as error:
            raise EnforcementFailure(refuse(
                status="refused",
                reason="The model did not produce a schema-valid process optimization proposal from the gathered evidence.",
                safe_next_step="Retry the request, or ask again with a narrower time range or different focus.",
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

    recommendation = _harden_process_change_recommendation(recommendation)
    bad_refs = unknown_reference_ids(recommendation.evidence_basis, evidence)
    if bad_refs:
        refusal = refuse(status="insufficient_evidence",
                         reason="The generated optimization proposal referenced evidence not supplied for this turn.",
                         missing_evidence=bad_refs,
                         safe_next_step="Retry using only the evidence supplied for this request.")
        return {"agent_result": {"schema": "S5", "output": refusal.model_dump(mode="json")},
                "evidence": evidence, "warnings": warnings}
    return {
        "agent_result": {"schema": "S7", "output": recommendation.model_dump(mode="json")},
        "evidence": evidence, "warnings": warnings,
        "human_approval_required": recommendation.human_approval_required,
        "action_class": "process_change",
    }
