"""Descriptive aggregates of stored records, never inferred plant state."""
from collections import Counter
from datetime import datetime, timezone
from time import perf_counter
from sqlalchemy import select, func
from app.db.models import AgentRun, AgentRunStep, IncidentReport, ActionRevision, ApprovalDecision, AuditEvent, OperatorNote


def snapshot(session):
    started = perf_counter()
    count = lambda model: session.scalar(select(func.count()).select_from(model))
    terminal = select(ApprovalDecision.action_revision_id).where(ApprovalDecision.decision.in_(("APPROVE", "REJECT")))
    pending = session.scalar(select(func.count()).select_from(ActionRevision).where(ActionRevision.id.not_in(terminal)))
    generated = dict(session.execute(select(AuditEvent.event_type, func.count()).where(AuditEvent.event_type.in_(
        ("HANDOVER_GENERATED", "COMPLIANCE_ASSESSMENT_GENERATED"))).group_by(AuditEvent.event_type)).all())
    maintenance = session.scalar(select(func.count()).select_from(ActionRevision).join(AgentRun,
        ActionRevision.originating_run_id == AgentRun.id).where(AgentRun.route.in_(("maintenance", "combined_safety_maintenance"))))
    # ponytail: latest 1000 runs bound JSON aggregation; add SQL/materialized aggregates for larger history.
    runs = session.scalars(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(1000)).all()
    steps = session.scalars(select(AgentRunStep).where(AgentRunStep.run_id.in_([r.id for r in runs]),
        AgentRunStep.node_name == "execution_metadata")).all() if runs else []
    executions = [s.usage.get("execution", {}) for s in steps]
    routes = Counter(r.route for r in runs)
    gaps = {g["gap_id"] for e in executions for g in e.get("knowledge_gaps", [])}
    latencies = [e["total_latency_ms"] for e in executions if isinstance(e.get("total_latency_ms"), (int, float))]
    generations = [e["generation_latency_ms"] for e in executions if isinstance(e.get("generation_latency_ms"), (int, float)) and e.get("model_call_count", 0) > 0]
    recent = session.scalars(select(AuditEvent).order_by(AuditEvent.sequence_number.desc()).limit(20)).all()
    return {"as_of": datetime.now(timezone.utc).isoformat(), "advisory_only": True,
        "scope": "internal", "sample_limit": 1000, "sampled_runs": len(runs), "metadata_runs": len(executions),
        "metrics": {"recorded_incidents": count(IncidentReport), "open_incidents": None,
            "pending_human_approvals": pending, "operator_notes": count(OperatorNote),
            "generated_handovers": generated.get("HANDOVER_GENERATED", 0),
            "environmental_assessments": generated.get("COMPLIANCE_ASSESSMENT_GENERATED", 0),
            "maintenance_advisory_revisions": maintenance,
            "knowledge_gaps_in_sample": len(gaps) if executions else None,
            "handover_runs_in_sample": routes["shift_handover"],
            "environmental_runs_in_sample": routes["environmental_compliance"],
            "maintenance_runs_in_sample": routes["maintenance"] + routes["combined_safety_maintenance"],
            "mean_query_latency_ms": sum(latencies)/len(latencies) if latencies else None,
            "mean_generation_latency_ms": sum(generations)/len(generations) if generations else None},
        "evidence_sufficiency": dict(Counter(e.get("evidence_sufficiency", {}).get("state", "UNKNOWN") for e in executions)),
        "execution_paths": dict(Counter(e.get("execution_path", "UNKNOWN") for e in executions)),
        "model_runtimes": dict(Counter(f"{r.runtime or 'unknown'} / {r.model or 'unknown'}" for r in runs)),
        "recent_audit": [{"event_type": a.event_type, "occurred_at": a.occurred_at, "sequence": a.sequence_number} for a in recent],
        "limitations": ["Incident records have no closure status; open incidents are unknown.",
            "Run counts are recorded attempts, not approved advisories or plant actions.",
            "Generated handovers and assessments count audit events; advisory revisions include unapproved drafts.",
            "Model/runtime labels on runs describe configuration; only nonzero recorded model calls enter generation latency.",
            "Pending review counts revisions without APPROVE/REJECT decisions; expired approvals are not pending.",
            "Sampled gaps are observed requests, not a complete unresolved-issue inventory."],
        "bi_latency_ms": (perf_counter()-started)*1000}
