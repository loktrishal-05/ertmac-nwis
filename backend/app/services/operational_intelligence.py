"""Deterministic local handover/compliance specialists. No execution tools."""
import json
import math
import re
from datetime import timezone
from uuid import UUID
from sqlalchemy import select
from app.db.models import User, OperatorNote, IncidentReport, SensorReading, Equipment
from app.schemas.operational import HandoverInput, ComplianceInput, LocalLimit
from app.agents.registry import invoke_tool
from app.agents.evidence import csv_row_evidence
from app.agents.enforcement import refuse
from app.services import operator_notes as notes, verified_knowledge as verified
from app.services.evidence_sufficiency import refs_as_models
from app.services.knowledge_gaps import detect

BOUNDARY = "Advisory only. Human reports and OCR do not establish isolation, LOTO, valve alignment, permit validity or readiness."
UNSAFE_REPORT = re.compile(r"isolat|loto|permit|line.?up|align|safe to|ready|de.?energ|lock.?out|tag.?out|cleared|permission|authorized|bypass|interlock|alarm|valve.*(?:open|clos)|start|stop", re.I)

def reported(text):
    return "Safety-state/action claim withheld; obtain authoritative field/permit evidence." if UNSAFE_REPORT.search(text or "") else text


def route_for(query):
    if re.search(r"\bshift[- ]handover\b", query, re.I): return "shift_handover"
    if re.search(r"\b(?:environmental compliance|environmental reading|emission|effluent|wastewater)\b", query, re.I): return "environmental_compliance"
    return None


def context_request(query, schema):
    marker = "\nOPERATIONAL_CONTEXT="
    if marker not in query: raise ValueError("Use the operational form with explicit evidence identifiers and bounded dates.")
    return schema.model_validate_json(query.split(marker, 1)[1])


def clarification(message):
    return {"agent_result": {"schema": "S5", "output": refuse(status="clarification_required", reason=message,
        missing_evidence=["explicit equipment/time window or reading and reviewed rule IDs"],
        safe_next_step="Use the authenticated operational Workspace form.").model_dump(mode="json")}, "evidence": [], "warnings": [BOUNDARY]}


def handover(session, payload, actor):
    verified.authorize(session, actor)
    asset = notes.equipment(session, payload.equipment_tag)
    refs, missing, warnings = [], [], [BOUNDARY]
    tool_data = {}
    for name, key, args in (("get_sensor_readings", "readings", {"equipment_tag": asset.equipment_tag, "start": payload.start, "end": payload.end, "limit": 200}),
                            ("get_maintenance_history", "records", {"equipment_tag": asset.equipment_tag, "start": payload.start, "end": payload.end, "limit": 100}),
                            ("retrieve_documents", "results", {"query": f"SOP for {asset.equipment_tag}", "document_types": ["sop"]})):
        try:
            data, evidence = invoke_tool(name, session, args)
            if name == "retrieve_documents":
                from app.agents.nodes.knowledge import _assess_evidence
                if not _assess_evidence(data)[0]: evidence = []
            tool_data[key] = data.get(key, []); refs += evidence
            if not evidence: missing.append({"gap_type": {"readings":"missing_sensor", "records":"missing_maintenance", "results":"missing_sop"}[key], "required_evidence": key})
            warnings += data.get("warnings", [])
        except Exception:
            tool_data[key] = []; missing.append({"gap_type": "tool_failure", "required_evidence": name})
    observations = [{"kind": "OBSERVATION", "sensor": r["sensor_tag"], "value": r["value"], "unit": r.get("unit"),
        "timestamp": r["timestamp"], "quality": r.get("quality"), "evidence_id": r["evidence_id"]} for r in tool_data["readings"]]
    activities = [{"kind": "HUMAN_REPORTED_INFORMATION", "text": reported(r["description"]),
        "recorded_status": r["status"], "evidence_id": r["evidence_id"]} for r in tool_data["records"]]
    reports = []
    rows = session.scalars(select(OperatorNote).where(OperatorNote.equipment_id == asset.id, OperatorNote.access_scope == "internal",
        OperatorNote.created_at >= payload.start, OperatorNote.created_at <= payload.end).order_by(OperatorNote.created_at).limit(100)).all()
    for row in rows:
        status = notes.review_state(session, row)
        if status in ("REJECTED", "REVOKED", "EXPIRED", "INVALID"):
            missing.append({"gap_type": "withdrawn_or_changed_report", "required_evidence": "current intact operator report"})
            continue
        ref = notes.evidence(session, row); refs.append(ref)
        reports.append({"kind": "HUMAN_REPORTED_INFORMATION", "text": reported(row.text), "author_id": str(row.author_id),
            "timestamp": row.created_at.isoformat(), "review_state": status, "evidence_id": ref.evidence_id})
    incidents = session.scalars(select(IncidentReport).where(IncidentReport.equipment_id == asset.id,
        IncidentReport.created_at >= payload.start, IncidentReport.created_at <= payload.end).limit(100)).all()
    for row in incidents:
        ref = notes.evidence(session, row, "incident_report"); refs.append(ref)
        reports.append({"kind": "HUMAN_REPORTED_INFORMATION", "text": reported(row.description),
            "recorded_severity": row.severity, "incident_status": "UNKNOWN", "evidence_id": ref.evidence_id})
    if not incidents: missing.append({"gap_type": "incident_status_unavailable", "required_evidence": "current incident status"})
    missing.append({"gap_type": "equipment_readiness_unestablished", "required_evidence": "authoritative current field and permit records"})
    gaps = detect(asset.equipment_tag, requests=missing, evidence=refs)
    output = {"shift_period": {"start": payload.start.isoformat(), "end": payload.end.isoformat()}, "equipment": asset.equipment_tag,
        "observations": observations, "human_reported_information": reports, "model_synthesis": [], "hypotheses": [],
        "synthesis_method": "DETERMINISTIC_EVIDENCE_ASSEMBLY", "ongoing_issues": [a for a in activities if (a["recorded_status"] or "").lower() not in ("completed", "closed")],
        "completed_actions": [a for a in activities if (a["recorded_status"] or "").lower() in ("completed", "closed")], "pending_actions": ["Qualified human review of handover and unresolved evidence"],
        "safety_relevant_notes": [BOUNDARY], "maintenance_context": activities, "unresolved_questions": gaps,
        "limitations": ["Recorded data only; latest/current conditions, complete interval coverage and incident closure are not inferred.",
                        "Recent advisories lack a reliable equipment link and are not automatically merged.", "Read limits: 200 sensor rows, 100 maintenance rows, 100 notes and 100 incidents."],
        "citations": [{"evidence_id": r.evidence_id, "locator": r.locator, "claim": "Recorded source; not operational clearance."} for r in refs],
        "human_approval_required": True}
    return {"agent_result": {"schema": "SHIFT_HANDOVER", "output": output}, "evidence": refs, "warnings": warnings,
            "gap_requests": missing, "operational_events": ["HANDOVER_GENERATED"]}


def compare_limit(value, unit, parameter, equipment_tag, timestamp, rules):
    missing = []
    if not rules: missing.append("missing_compliance_threshold")
    if not math.isfinite(value): missing.append("invalid_measurement")
    for rule in rules:
        if rule.unit != unit: missing.append("unit_mismatch")
        if rule.parameter != parameter or rule.equipment_tag != equipment_tag: missing.append("rule_applicability_mismatch")
        if not rule.valid_from <= timestamp <= rule.valid_to: missing.append("rule_outside_validity_period")
    if len({r.upper_limit for r in rules}) > 1: missing.append("conflicting_rule_documents")
    limit = rules[0].upper_limit if rules and not missing else None
    status = "INDETERMINATE" if missing else ("EXCEEDS_DOCUMENTED_LIMIT" if value > limit else "WITHIN_DOCUMENTED_LIMIT")
    return status, limit, sorted(set(missing))


def compliance(session, payload, actor):
    verified.authorize(session, actor)
    row = session.get(SensorReading, payload.reading_id)
    if row is None: return clarification("Requested local measurement is unavailable.")
    asset = session.get(Equipment, row.equipment_id)
    stamp = row.timestamp if row.timestamp.tzinfo else row.timestamp.replace(tzinfo=timezone.utc)
    ref = csv_row_evidence(source_filename=row.source_filename, source_sha256=row.source_sha256, source_row_number=row.source_row_number)
    refs, rules, missing = [ref], [], []
    for rule_id in dict.fromkeys(payload.rule_ids):
        try:
            item = verified.inspect_item(session, rule_id, actor)
            if item.status != "VERIFIED": raise ValueError("Rule not currently verified")
            rule = LocalLimit.model_validate_json(item.statement)
            # Machine-readable local rule must also exist verbatim in the reviewed source.
            if not any(item.statement in r.get("quote", "") for r in item.evidence): raise ValueError("Rule not source-bound")
            rules.append(rule); refs += refs_as_models(item.evidence)
        except (ValueError, verified.KnowledgeConflict):
            missing.append("stale_or_unavailable_rule")
    status, limit, issues = compare_limit(row.value, row.unit, row.sensor_type, asset.equipment_tag, stamp, rules)
    missing += issues
    if (row.quality or "").lower() not in ("good", "valid", "ok"): missing.append("measurement_quality_unestablished")
    if missing: status, limit = "INDETERMINATE", None
    requests = [{"gap_type": x, "required_evidence": "current applicable reviewed environmental rule and compatible measurement"} for x in sorted(set(missing))]
    output = {"parameter": row.sensor_type, "observed_value": row.value if math.isfinite(row.value) else None, "unit": row.unit, "observed_at": stamp.isoformat(),
        "equipment": asset.equipment_tag, "applicable_rule_ids": [str(x) for x in payload.rule_ids], "limit": limit, "status": status,
        "comparison_basis": "instantaneous upper bound from human-reviewed local rule; not legal certification",
        "missing_evidence": sorted(set(missing)), "recommended_human_follow_up": "Qualified environmental reviewer must confirm applicability, measurement quality and follow-up.",
        "citations": [{"evidence_id": r.evidence_id, "locator": r.locator, "claim": "Local supplied measurement or reviewed rule."} for r in refs],
        "human_approval_required": True}
    return {"agent_result": {"schema": "ENVIRONMENTAL_COMPLIANCE", "output": output}, "evidence": refs,
            "warnings": [BOUNDARY], "gap_requests": requests, "operational_events": ["COMPLIANCE_ASSESSMENT_GENERATED"]}


def operational_node(state, session):
    actor = session.get(User, UUID(state["actor_id"])) if state.get("actor_id") else None
    verified.authorize(session, actor)
    try:
        if state["route"] == "shift_handover": return handover(session, context_request(state["query"], HandoverInput), actor)
        return compliance(session, context_request(state["query"], ComplianceInput), actor)
    except ValueError as error:
        return clarification(str(error))
