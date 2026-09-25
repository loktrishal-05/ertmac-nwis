"""Persists one AgentRun row (+ one AgentRunStep row per graph step) after
run_graph() returns.

Only evidence_id STRINGS ever reach these tables — never an EvidenceRef
body, never retrieved document text, never an OCR region quote, never a
sensor row value. The operator's own query text is stored only when
AGENT_TRACE_STORE_QUERY is true. Phase 5A can require a minimal originating
run even when optional tracing is disabled, and share its transaction."""
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.state import WorkbenchState
from app.core.config import settings
from app.db.models.agent_run import AgentRun
from app.db.models.agent_run_step import AgentRunStep


def _parse(timestamp: str | None) -> datetime | None:
    return datetime.fromisoformat(timestamp) if timestamp else None


def record_run(
    session: Session,
    state: WorkbenchState,
    *,
    status: str,
    model: str | None,
    runtime: str | None,
    error: str | None = None,
    required: bool = False,
    commit: bool = True,
) -> AgentRun | None:
    if not settings.agent_trace_enabled and not required:
        return None

    started_at = _parse(state.get("started_at"))
    finished_at = _parse(state.get("finished_at"))
    duration_ms = (
        (finished_at - started_at).total_seconds() * 1000
        if started_at and finished_at
        else None
    )

    run = AgentRun(
        id=uuid.UUID(state["run_id"]),
        query_text=state["query"] if settings.agent_trace_enabled and settings.agent_trace_store_query else None,
        route=state.get("route"),
        route_confidence=state.get("route_confidence"),
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        error=error,
        model=model,
        runtime=runtime,
        gateway_repair_attempts=state.get("gateway_repair_attempts", 0),
        warnings=list(state.get("warnings", [])),
    )
    session.add(run)
    session.flush()

    for index, step in enumerate(state.get("step_records", []) if settings.agent_trace_enabled else []):
        session.add(
            AgentRunStep(
                run_id=run.id,
                step_index=index,
                node_name=step.get("node_name", ""),
                started_at=_parse(step.get("started_at")),
                finished_at=_parse(step.get("finished_at")),
                duration_ms=step.get("duration_ms"),
                tool_name=step.get("tool_name"),
                evidence_ids=list(step.get("evidence_ids", [])),
                usage=dict(step.get("usage") or {}),
                timings=dict(step.get("timings") or {}),
                warnings=list(step.get("warnings", [])),
                error=step.get("error"),
            )
        )

    if state.get("execution"):
        session.add(AgentRunStep(run_id=run.id, step_index=len(state.get("step_records", [])),
            node_name="execution_metadata", usage={"execution": state["execution"]},
            timings={}, evidence_ids=[], warnings=[]))

    if commit:
        session.commit()
        session.refresh(run)
    return run
