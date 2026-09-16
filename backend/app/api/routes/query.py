"""Runs the Phase 4B router graph. No route beyond routing itself reasons
yet; every route resolves to its stub node's not_implemented result."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.graph import run_graph
from app.agents.tracing import record_run
from app.core.config import settings
from app.db.session import get_db
from app.schemas.query import QueryRequest, QueryResponse
from app.services.model_gateway import ModelRuntimeError, ModelTimeoutError, ModelUnavailableError

router = APIRouter(tags=["query"])


def _timings(state: dict) -> dict:
    return {
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "steps": [
            {"node_name": step.get("node_name"), "duration_ms": step.get("duration_ms")}
            for step in state.get("step_records", [])
        ],
    }


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, session: Session = Depends(get_db)) -> QueryResponse:
    try:
        state = run_graph(request.query, session=session)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ModelTimeoutError as error:
        raise HTTPException(status_code=504, detail="Model gateway timed out.") from error
    except ModelUnavailableError as error:
        raise HTTPException(status_code=503, detail="Model runtime is unavailable.") from error
    except ModelRuntimeError as error:
        raise HTTPException(status_code=502, detail="Model runtime returned an error.") from error

    status = "error" if state.get("errors") else "ok"
    record_run(
        session, state, status=status,
        model=settings.model_name, runtime=settings.model_runtime,
        error="; ".join(state.get("errors", [])) or None,
    )

    return QueryResponse(
        run_id=state["run_id"], route=state.get("route"), route_confidence=state.get("route_confidence"),
        route_reasoning=state.get("route_reasoning"), agent_result=state.get("agent_result"),
        evidence=state.get("evidence", []), warnings=state.get("warnings", []),
        human_approval_required=state.get("human_approval_required", False),
        action_class=state.get("action_class"), timings=_timings(state),
    )
