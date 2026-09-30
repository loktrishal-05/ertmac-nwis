"""Descriptive aggregates of stored records, never inferred plant state."""
from collections import Counter
from app.services.ui_reads import now, utc, approval_state
from datetime import datetime, timezone
from time import perf_counter
from sqlalchemy import select, func
from app.db.models import AgentRun, AgentRunStep, IncidentReport, ActionRevision, ApprovalDecision, AuditEvent, OperatorNote


def dashboard(session, start, end):
    """Latest 1000 rows per cohort inside a half-open UTC window; never extrapolated."""
    # ponytail: bounded recent cohorts; use SQL time-bucket aggregates if complete high-volume history is needed.
    from app.db.models import VerifiedKnowledge, KnowledgeGap
    from app.db.models.durable_execution import DurableExecution
    cap = 1000
    at = now()
    samples = {}
    def sample(name, model, clock, query=None):
        query = query if query is not None else select(model)
        rows = session.execute(query.where(clock >= start, clock < end)
            .order_by(clock.desc(), model.id.desc()).limit(cap + 1)).all()
        samples[name] = {"sample_size": min(len(rows), cap), "truncated": len(rows) > cap,
                         "limit": cap, "as_of": at}
        return rows[:cap]
    # Select only operational columns, never query text.
    run_rows = sample("runs", AgentRun, AgentRun.created_at,
        select(AgentRun.id, AgentRun.created_at, AgentRun.route, AgentRun.model))
    runs = [r.id for r in run_rows]
    steps = session.execute(select(AgentRunStep.run_id, AgentRunStep.usage)
        .where(AgentRunStep.run_id.in_(runs), AgentRunStep.node_name == "execution_metadata")
        .order_by(AgentRunStep.run_id, AgentRunStep.step_index.desc(), AgentRunStep.id.desc())
        .limit(cap * 2 + 1)).all() if runs else []
    metadata = {}
    for ident, usage in steps:
        value = (usage or {}).get("execution")
        if isinstance(value, dict):
            metadata.setdefault(ident, value)
    recorded = list(metadata.values())
    bucket = "hour" if (end - start).total_seconds() <= 86400 else "day"
    def bucket_at(value):
        value = utc(value).replace(minute=0, second=0, microsecond=0)
        return value if bucket == "hour" else value.replace(hour=0)
    volume = Counter(bucket_at(r.created_at).isoformat() for r in run_rows)
    selected = [e.get("model_selected") or e.get("selected_model") for e in recorded]
    selected = [m for m in selected if m]
    escalations = [e["escalated"] for e in recorded if isinstance(e.get("escalated"), bool)]
    evidence = [e["evidence_sufficiency"]["state"] for e in recorded
                if isinstance(e.get("evidence_sufficiency"), dict) and e["evidence_sufficiency"].get("state")]
    executions = sample("executions", DurableExecution, DurableExecution.created_at,
        select(DurableExecution.id, DurableExecution.status))
    approvals = sample("approvals", ActionRevision, ActionRevision.created_at,
        select(ActionRevision.id, approval_state(at).label("state")))
    decisions = sample("decisions", ApprovalDecision, ApprovalDecision.decided_at,
        select(ApprovalDecision.id, ApprovalDecision.decision, ApprovalDecision.decided_at, ActionRevision.created_at)
            .join(ActionRevision, ActionRevision.id == ApprovalDecision.action_revision_id))
    latency = [(utc(d.decided_at) - utc(d.created_at)).total_seconds() for d in decisions
               if d.decision in ("APPROVE", "REJECT") and utc(d.decided_at) >= utc(d.created_at)]
    knowledge = sample("knowledge", VerifiedKnowledge, VerifiedKnowledge.created_at,
        select(VerifiedKnowledge.id, VerifiedKnowledge.status).where(VerifiedKnowledge.access_scope == "internal"))
    gaps = sample("knowledge_gaps", KnowledgeGap, KnowledgeGap.created_at,
        select(KnowledgeGap.id, KnowledgeGap.status).where(KnowledgeGap.access_scope == "internal"))
    audits = sample("audit", AuditEvent, AuditEvent.occurred_at,
        select(AuditEvent.id, AuditEvent.event_type, AuditEvent.occurred_at))
    samples["metadata"] = {"sample_size": len(recorded), "missing_runs": len(runs) - len(recorded),
                            "truncated": len(steps) > cap * 2, "as_of": at}
    def distribution(values):
        return {"counts": dict(Counter(values)) if values else None, "sample_size": len(values)}
    return {"as_of": at, "window": {"start": start, "end": end, "semantics": "[start,end)"},
        "advisory_only": True, "samples": samples, "sample_limit": cap,
        "query_volume": {"bucket": bucket, "points": [{"at": k, "count": v} for k, v in sorted(volume.items())],
                         "sample_size": len(runs), "source": "persisted_agent_runs"},
        "model_routing": distribution(selected),
        "escalations": {"count": sum(escalations) if escalations else None, "sample_size": len(escalations)},
        "execution_status": distribution([r.status for r in executions]),
        "pending_approvals": {"count": sum(r.state == "PENDING_REVIEW" for r in approvals),
                              "sample_size": len(approvals)},
        "approval_status": distribution([r.state for r in approvals]),
        "approval_outcomes": distribution([d.decision for d in decisions]),
        "approval_latency_seconds": {"mean": sum(latency) / len(latency) if latency else None,
                                     "sample_size": len(latency)},
        "knowledge_lifecycle": distribution([r.status for r in knowledge]),
        "knowledge_gap_status": distribution([r.status for r in gaps]),
        "evidence_sufficiency": distribution(evidence),
        "audit_activity": distribution([r.event_type for r in audits]),
        "service_status": None,
        "limitations": [
            "Counts cover bounded stored cohorts, not all system traffic; truncated cohorts are partial.",
            "Volume omits attempts without persisted AgentRun records; absent time buckets are not filled.",
            "Routing is recorded selection, not proof of model calls. Missing metadata is unavailable.",
            "Status counts are current recorded states of objects created in the window, not historical snapshots.",
            "Knowledge statuses are last validated ledger states; inspect/revalidate to check source freshness.",
            "Gap counts cover persisted review records; unpersisted detected gaps remain in /knowledge-gaps.",
            "Decision outcomes use decision time; latency excludes revocations and invalid timestamp pairs.",
            "Use existing /health, /models/status and /product/status for authoritative service probes."
        ]}


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
