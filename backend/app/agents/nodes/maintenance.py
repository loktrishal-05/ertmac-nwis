"""The maintenance & asset reliability agent (Phase 4E). Emits S4 (general
maintenance assessment), S6 (sensor-window interpretation, via the
threshold loop), or S5 (refusal).

The safety property this sub-phase enforces in code: the model never
performs arithmetic or asserts a threshold, and observations never name a
failure mode.

The threshold loop (see _threshold_loop below) is the centerpiece: a
numeral is located in cited SOP text by a deterministic regex
(_extract_threshold), never guessed or computed by the model; that numeral
is passed into compute_sensor_features (app/agents/tools/sensors.py,
already built in 4B, which deliberately invents no default threshold), and
the actual comparison happens inside Phase 3C's own
app.services.sensor_features.detect_anomalies -- Python code, not a model
call. A SOP citation is required before any threshold is used at all: if no
SOP text yields a numeral, the loop is never entered (see D-014)."""
import json
import re
from datetime import datetime, timedelta, timezone

from app.agents.enforcement import (
    EnforcementFailure,
    enforce_citations_and_diagnostic_language,
    unknown_reference_ids,
    refuse,
)
from app.agents.prompts.maintenance import (
    MAINTENANCE_ASSESSMENT_SYSTEM_PROMPT,
    SENSOR_INTERPRETATION_SYSTEM_PROMPT,
    build_maintenance_user_message,
    format_evidence_block,
    format_evidence_ref,
)
from app.agents.registry import invoke_tool
from app.agents.pid_evidence import is_ocr, pid_evidence_lookup, drawing_refusal, drawing_citations
from app.schemas.agent_outputs import Citation, MaintenanceAssessment, SensorInterpretation, SensorObservation
from app.services.model_gateway import ChatMessage, StructuredOutputError, get_model_gateway
from app.services.sparse import identifiers as extract_identifiers

SUB_PHASE = "4E"

# Provisional, D-014: a fixed lookback window for the threshold loop's sensor
# query, since the query text carries no explicit time range of its own.
_THRESHOLD_WINDOW_DAYS = 7
_MAX_HISTORY_ROWS = 20

# Provisional, D-014: a deterministic numeral extractor over SOP text. Matches
# "maximum/max/limit/threshold/upper limit/(shall) not exceed" followed within
# 15 characters by a number -- never a model guess.
_THRESHOLD_PATTERN = re.compile(
    r"(?:maximum|max|limit|not exceed|shall not exceed|threshold|upper limit)\D{0,15}?(-?\d+(?:\.\d+)?)\s*([A-Za-z/%°]+)?",
    re.IGNORECASE,
)

_CRITICAL_KINDS = {"threshold_exceeded", "threshold_below"}
_WARNING_KINDS = {"sudden_change", "missing_samples", "stale_sensor", "bad_quality",
                   "relative_increase", "relative_decrease"}


def _extract_threshold(sop_refs, *, equipment_tag=None, measurement=None, unit=None):
    """Return a limit only when asset, measurement, and unit are applicable."""
    if not all((equipment_tag, measurement, unit)):
        return None, None
    for ref in sop_refs:
        quote = getattr(ref, "quote", None) or ""
        match = _THRESHOLD_PATTERN.search(quote)
        lowered = quote.lower()
        if match and all(str(value).lower() in lowered for value in (equipment_tag, measurement, unit)):
            try:
                return ref, float(match.group(1))
            except ValueError:
                continue
    return None, None


def _anomaly_status(raw_observations: list[dict]) -> str:
    kinds = {observation["kind"] for observation in raw_observations}
    if kinds & _CRITICAL_KINDS:
        return "critical"
    if kinds & _WARNING_KINDS:
        return "warning"
    return "normal"


def _row_block(evidence_id: str, locator: str, row: dict) -> str:
    payload = {key: value for key, value in row.items() if key != "evidence_id"}
    return format_evidence_block(evidence_id, locator, json.dumps(payload, default=str))


def maintenance_node(state, gateway=None, session=None) -> dict:
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
    doc_blocks = []

    doc_payload, doc_refs = invoke_tool("retrieve_documents", session, {"query": query})
    doc_refs, drawing_warnings = pid_evidence_lookup(query, doc_refs, session)
    warnings += drawing_warnings
    warnings += doc_payload.get("warnings", [])
    evidence += doc_refs
    doc_refs = [ref for ref in doc_refs if not is_ocr(ref)]
    for ref in doc_refs:
        doc_blocks.append(format_evidence_ref(ref))

    hist_payload, hist_refs = invoke_tool(
        "get_maintenance_history", session, {"equipment_tag": tag, "limit": _MAX_HISTORY_ROWS},
    )
    warnings += hist_payload.get("warnings", [])
    evidence += hist_refs
    history_blocks = [
        _row_block(ref.evidence_id, ref.locator, row)
        for row, ref in zip(hist_payload.get("records", []), hist_refs)
    ]

    latest_payload, latest_refs = invoke_tool("get_latest_reading", session, {"equipment_tag": tag})
    latest_readings = latest_payload.get("readings", [])

    sensor_tag = latest_readings[0]["sensor_tag"] if latest_readings else None
    sensor_measurement = latest_readings[0].get("measurement") or latest_readings[0].get("sensor_type") if latest_readings else None
    sensor_unit = latest_readings[0].get("unit") if latest_readings else None
    sop_ref, threshold_value = _extract_threshold(
        doc_refs, equipment_tag=tag, measurement=sensor_measurement or sensor_tag, unit=sensor_unit,
    )

    if sop_ref is not None and sensor_tag is not None:
        return _threshold_loop(
            state, gateway, session, tag=tag, sensor_tag=sensor_tag, sop_ref=sop_ref,
            threshold_value=threshold_value, evidence=list(evidence), warnings=list(warnings),
            fallback_blocks=doc_blocks + history_blocks,
        )

    evidence += latest_refs
    if sop_ref is None:
        warnings.append("threshold unavailable / insufficient authoritative limit evidence")
    latest_blocks = [
        _row_block(ref.evidence_id, ref.locator, row)
        for row, ref in zip(latest_readings, latest_refs)
    ]
    return _general_assessment(
        state, gateway, tag=tag, evidence=evidence, warnings=warnings,
        blocks=doc_blocks + history_blocks + latest_blocks,
    )


def _general_assessment(state, gateway, *, tag, evidence, warnings, blocks):
    authoritative = [ref for ref in evidence if not is_ocr(ref)]
    if evidence and not authoritative:
        return drawing_refusal(state['query'], evidence)
    if not evidence:
        refusal = refuse(
            status="insufficient_evidence",
            reason=f"No SOP, maintenance history, or sensor evidence was found for {tag}.",
            missing_evidence=[tag],
            safe_next_step="Confirm the equipment tag is correct, or ask again once records exist for it.",
        )
        return {"agent_result": {"schema": "S5", "output": refusal.model_dump(mode="json")},
                "evidence": evidence, "warnings": warnings}

    def _generate(retry_note: str | None) -> MaintenanceAssessment:
        messages = [
            ChatMessage(role="system", content=MAINTENANCE_ASSESSMENT_SYSTEM_PROMPT),
            ChatMessage(role="user", content=build_maintenance_user_message(state["query"], tag, blocks)),
        ]
        if retry_note:
            messages.append(ChatMessage(role="user", content=retry_note))
        try:
            result = gateway.generate_structured(messages=messages, schema=MaintenanceAssessment, think=False)
        except StructuredOutputError as error:
            raise EnforcementFailure(refuse(
                status="refused",
                reason="The model did not produce a schema-valid maintenance assessment from the gathered evidence.",
                safe_next_step="Retry the request, or ask again with a narrower time range.",
            )) from error
        return result.value

    try:
        assessment = enforce_citations_and_diagnostic_language(
            generate=_generate, extract_citations=lambda value: value.citations,
            extract_observation_text=lambda value: " ".join(value.observations), available=authoritative,
            require_citations=True,
        )
    except EnforcementFailure as failure:
        return {"agent_result": {"schema": "S5", "output": failure.refusal.model_dump(mode="json")},
                "evidence": evidence, "warnings": warnings}

    referenced = [item for hypothesis in assessment.hypotheses
                  for item in (*hypothesis.supporting_evidence, *hypothesis.contradicting_evidence)]
    bad_refs = unknown_reference_ids(referenced, authoritative)
    if bad_refs:
        refusal = refuse(status="insufficient_evidence",
                         reason="The generated assessment referenced evidence not supplied for this turn.",
                         missing_evidence=bad_refs,
                         safe_next_step="Retry with the supplied equipment records and citations.")
        return {"agent_result": {"schema": "S5", "output": refusal.model_dump(mode="json")},
                "evidence": evidence, "warnings": warnings}

    assessment = assessment.model_copy(update={'citations': assessment.citations + drawing_citations(evidence)})
    return {"agent_result": {"schema": "S4", "output": assessment.model_dump(mode="json")},
            "evidence": evidence, "warnings": warnings}


def _threshold_loop(state, gateway, session, *, tag, sensor_tag, sop_ref, threshold_value, evidence, warnings,
                     fallback_blocks):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=_THRESHOLD_WINDOW_DAYS)
    sensor_payload, sensor_refs = invoke_tool("compute_sensor_features", session, {
        "equipment_tag": tag, "sensor_tag": sensor_tag,
        "start": start.isoformat(), "end": end.isoformat(),
        "thresholds": {"maximum": threshold_value},
    })
    evidence = evidence + sensor_refs
    sensor_ref = sensor_refs[0] if sensor_refs else None
    raw_observations = sensor_payload.get("observations", [])

    if sensor_ref is None or not raw_observations:
        # Nothing crossed the cited threshold in this window; the SOP/history
        # evidence already gathered is still real evidence for a general read,
        # so fall through to S4 rather than refuse outright.
        return _general_assessment(state, gateway, tag=tag, evidence=evidence, warnings=warnings, blocks=fallback_blocks)

    sensor_observations = [
        SensorObservation(
            metric=sensor_payload.get("measurement") or sensor_tag,
            value_or_trend=observation["observation"], evidence_id=sensor_ref.evidence_id,
        )
        for observation in raw_observations
    ]
    anomaly_status = _anomaly_status(raw_observations)
    time_window = f"{sensor_payload.get('window_start')} to {sensor_payload.get('window_end')}"
    citations = [
        Citation(evidence_id=sop_ref.evidence_id, locator=sop_ref.locator,
                 claim=f"SOP-cited threshold used for this comparison: {threshold_value}"),
        Citation(evidence_id=sensor_ref.evidence_id, locator=sensor_ref.locator,
                 claim="Sensor readings evaluated against the cited threshold"),
    ]

    blocks = [
        format_evidence_ref(sop_ref),
        format_evidence_block(sensor_ref.evidence_id, sensor_ref.locator, json.dumps(raw_observations, default=str)),
    ]

    messages = [
        ChatMessage(role="system", content=SENSOR_INTERPRETATION_SYSTEM_PROMPT),
        ChatMessage(role="user", content=build_maintenance_user_message(state["query"], tag, blocks)),
    ]
    try:
        result = gateway.generate_structured(messages=messages, schema=SensorInterpretation, think=False)
        interpretation = result.value
    except StructuredOutputError:
        refusal = refuse(
            status="refused",
            reason="The model did not produce a schema-valid sensor interpretation from the gathered evidence.",
            safe_next_step="Retry the request, or ask again with a narrower time range.",
        )
        return {"agent_result": {"schema": "S5", "output": refusal.model_dump(mode="json")},
                "evidence": evidence, "warnings": warnings}

    hypothesis_refs = [item for hypothesis in interpretation.hypotheses
                       for item in (*hypothesis.supporting_evidence, *hypothesis.contradicting_evidence)]
    bad_refs = unknown_reference_ids(hypothesis_refs, [ref for ref in evidence if not is_ocr(ref)])
    if bad_refs:
        refusal = refuse(status="insufficient_evidence",
                         reason="The generated sensor interpretation referenced evidence not supplied for this turn.",
                         missing_evidence=bad_refs,
                         safe_next_step="Retry with the supplied sensor evidence.")
        return {"agent_result": {"schema": "S5", "output": refusal.model_dump(mode="json")},
                "evidence": evidence, "warnings": warnings}

    # The deterministic fields are never taken from the model, regardless of what
    # it returned: observations/anomaly_status/citations/asset_tag/time_window
    # are entirely Python-computed, per this sub-phase's safety property.
    hardened = interpretation.model_copy(update={
        "asset_tag": tag, "time_window": time_window, "observations": sensor_observations,
        "anomaly_status": anomaly_status, "citations": citations + drawing_citations(evidence),
    })
    return {"agent_result": {"schema": "S6", "output": hardened.model_dump(mode="json")},
            "evidence": evidence, "warnings": warnings}
