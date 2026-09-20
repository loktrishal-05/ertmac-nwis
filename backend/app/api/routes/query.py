"""Validated specialist output enters the common Phase 5A boundary."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.graph import GraphExecutionError, run_graph
from app.agents.tracing import record_run
from app.core.config import settings
from app.db.session import get_db
from app.schemas.query import QueryRequest, QueryResponse
from app.services.model_gateway import ModelRuntimeError, ModelTimeoutError, ModelUnavailableError
from app.services.governance import GovernanceConflict, govern_response, replay_request

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, session: Session = Depends(get_db)) -> QueryResponse:
    try:
        replayed = replay_request(session, request)
        if replayed is not None:
            return replayed
        state = run_graph(request.query, session=session, access_scope=request.access_scope)
    except GovernanceConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except GraphExecutionError as wrapped:
        session.rollback()
        try:
            record_run(session, wrapped.state, status="error", model=settings.model_name,
                       runtime=settings.model_runtime, error=str(wrapped.original))
        except Exception:
            session.rollback()
        error = wrapped.original
        if isinstance(error, ModelTimeoutError):
            raise HTTPException(status_code=504, detail="Model gateway timed out.") from error
        if isinstance(error, ModelUnavailableError):
            raise HTTPException(status_code=503, detail="Model runtime is unavailable.") from error
        if isinstance(error, ModelRuntimeError):
            raise HTTPException(status_code=502, detail="Model runtime returned an error.") from error
        raise
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ModelTimeoutError as error:
        raise HTTPException(status_code=504, detail="Model gateway timed out.") from error
    except ModelUnavailableError as error:
        raise HTTPException(status_code=503, detail="Model runtime is unavailable.") from error
    except ModelRuntimeError as error:
        raise HTTPException(status_code=502, detail="Model runtime returned an error.") from error

    try:
        return govern_response(session, request, state)
    except GovernanceConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
