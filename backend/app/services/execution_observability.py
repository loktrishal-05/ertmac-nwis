"""Request-local counters: no prompts, responses or private reasoning recorded."""
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
from time import perf_counter

_current = ContextVar("execution_metrics", default=None)
_stage = ContextVar("execution_stage", default="generation")


def observe_query(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        token = _current.set({"started": perf_counter(), "calls": [], "tools": []})
        try: return fn(*args, **kwargs)
        finally: _current.reset(token)
    return wrapped


@contextmanager
def stage(name):
    token = _stage.set(name)
    try: yield
    finally: _stage.reset(token)


def record_model(model, elapsed, result=None):
    current = _current.get()
    if current is not None:
        current["calls"].append({"stage": _stage.get(), "model": model, "latency_ms": elapsed,
            "input_tokens": result.usage.prompt_tokens if result else None,
            "output_tokens": result.usage.completion_tokens if result else None,
            "failed": result is None})


def record_tool(name, elapsed, failed):
    current = _current.get()
    if current is not None:
        current["tools"].append({"name": name, "latency_ms": elapsed, "failed": failed})


def attach(session, request, state, meta):
    from app.services.evidence_sufficiency import assess, refs_as_models, source_valid, categories_for
    current = _current.get() or {"started": perf_counter(), "calls": [], "tools": []}
    refs = refs_as_models(state.get("evidence", []))
    invalid = [r.evidence_id for r in refs if not source_valid(session, r, request.access_scope)]
    output = (state.get("agent_result") or {}).get("output") or {}
    sufficiency = assess(request.query, refs, invalid_ids=invalid,
        tool_failed=any(t["failed"] for t in current["tools"]), citations=output.get("citations", []),
        multi_document=bool(state.get("mgs_group_count")) or meta.get("selected_path") == "MGS_PATH",
        categories=categories_for(session, refs))
    if output.get("status") == "insufficient_evidence":
        sufficiency["state"] = "INSUFFICIENT"
        sufficiency["issues"].append("answer_evidence_insufficient")
    from app.services.knowledge_gaps import detect
    from app.services.canonicalization import canonical_hash
    subject = output.get("equipment") or "query:" + canonical_hash(request.query)
    gaps = detect(subject, sufficiency, state.get("gap_requests", []), refs)
    if output.get("status") in ("refused", "clarification_required"):
        gaps = []  # No evidentiary answer was attempted on these terminal paths.
    if state.get("gap_requests") and sufficiency["state"] == "SUFFICIENT": sufficiency["state"] = "PARTIAL"
    if output.get("status") == "INDETERMINATE": sufficiency["state"] = "INSUFFICIENT"
    if gaps:
        state["operational_events"] = list(dict.fromkeys(state.get("operational_events", []) + ["KNOWLEDGE_GAPS_IDENTIFIED"]))
    calls = current["calls"]
    def tokens(key):
        return sum(c[key] for c in calls) if all(c[key] is not None for c in calls) else None
    execution = {"execution_path": meta.get("selected_path", "EXISTING_AGENTIC_PATH"),
        "selection_source": meta.get("selection_source", "deterministic"), "reason_code": meta.get("reason_code"),
        "fallback_reason": meta.get("fallback_reason"),
        "fallback_used": meta.get("selection_source") == "fallback",
        "knowledge_id": meta.get("knowledge_id"), "pack_id": meta.get("pack_id"), "pack_version": meta.get("pack_version"),
        "retrieved_document_count": len({getattr(r, "document_id", None) for r in refs if getattr(r, "document_id", None)}),
        "retrieved_sources": len({r.source_sha256 for r in refs}), "evidence_count": len(refs),
        "mgs_group_count": state.get("mgs_group_count", 0),
        "knowledge_gaps": gaps, "evidence_sufficiency": sufficiency, "model_used": sorted({c["model"] for c in calls}),
        "model_call_count": len(calls), "model_stages": calls,
        "input_tokens": tokens("input_tokens"), "output_tokens": tokens("output_tokens"),
        "retrieval_latency_ms": sum(t["latency_ms"] for t in current["tools"]),
        "generation_latency_ms": sum(c["latency_ms"] for c in calls),
        "total_latency_ms": (perf_counter() - current["started"]) * 1000}
    if sufficiency["state"] != "SUFFICIENT":
        state.setdefault("warnings", []).append("Evidence coverage: " + sufficiency["state"] +
            "; missing: " + ", ".join(sufficiency["missing_categories"] + sufficiency["issues"]))
    state["execution"] = execution
    return execution


def measure_model(fn):
    @wraps(fn)
    def wrapped(self, *args, **kwargs):
        started = perf_counter(); result = None
        try:
            result = fn(self, *args, **kwargs)
            return result
        finally:
            record_model(self._settings.model_name, (perf_counter() - started) * 1000, result)
    return wrapped


def stored_execution(session, run_id):
    from sqlalchemy import select
    from app.db.models.agent_run_step import AgentRunStep
    row = session.scalars(select(AgentRunStep).where(AgentRunStep.run_id == run_id,
        AgentRunStep.node_name == "execution_metadata")).first()
    return row.usage.get("execution") if row else None
