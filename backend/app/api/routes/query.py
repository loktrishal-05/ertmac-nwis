"""Validated specialist output enters the common Phase 5A/5B boundary.

Phase 5E's deterministic preflight (app.services.preflight) runs after replay
handling (an already-governed request_id must keep replaying its original
committed draft unchanged) but strictly BEFORE run_graph -- a REFUSE/CLARIFY
decision returns without ever invoking the LangGraph router or the model
gateway (docs/phase5e.md, "Zero-model-call behavior")."""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.graph import GraphExecutionError, run_graph
from app.agents.tracing import record_run
from app.api.deps import get_optional_current_user
from app.core.config import settings
from app.db.models import User
from app.db.session import get_db
from app.schemas.query import QueryRequest, QueryResponse
from app.services.audit import append_event
from app.services.model_gateway import ModelRuntimeError, ModelTimeoutError, ModelUnavailableError
from app.services.governance import GovernanceConflict, govern_response, replay_request
from app.services.preflight import PreflightResult, run_preflight

router = APIRouter(tags=["query"])

_PREFLIGHT_EVENT_TYPES = {
    "unsupported_access_scope": "PREFLIGHT_SCOPE_DENIED",
    "prompt_injection_detected": "PREFLIGHT_INJECTION_REFUSED",
    "unsafe_action_request": "PREFLIGHT_UNSAFE_ACTION_REFUSED",
    "out_of_scope": "PREFLIGHT_OUT_OF_SCOPE_REFUSED",
    "ambiguous_domain": "PREFLIGHT_CLARIFICATION_REQUIRED",
}


def _preflight_response(request: QueryRequest, preflight: PreflightResult) -> QueryResponse:
    return QueryResponse(
        request_id=request.request_id or uuid4(), run_id=str(uuid4()), route=None,
        route_confidence=None, route_reasoning=None,
        agent_result={"schema": "S5", "output": preflight.refusal.model_dump(mode="json")},
        evidence=[], warnings=[], human_approval_required=False, action_class=None, timings={},
        governance_status="INFORMATIONAL", human_review_required=False, presentation="INFORMATIONAL",
    )


def _audit_preflight_denial(session: Session, request: QueryRequest, preflight: PreflightResult,
                           actor: User | None) -> None:
    """Best-effort (docs/phase5c.md "Atomic governance/audit behavior"): a
    REFUSE/CLARIFY preflight response is not an authoritative state change --
    nothing else commits alongside it -- so a failure here must never turn an
    already-correct 200 refusal/clarification body into a 500. Never logs the
    raw query text (Phase 5E brief: "Never log secrets"), only the deterministic
    reason code, domain status, and risk category labels."""
    event_type = _PREFLIGHT_EVENT_TYPES[preflight.reason_code]
    try:
        append_event(
            session, event_type=event_type, actor_id=actor.id if actor else None,
            actor_kind="user" if actor else "anonymous",
            payload={"decision": preflight.decision, "domain_status": preflight.domain_status,
                    "reason_code": preflight.reason_code, "detected_risks": preflight.detected_risks,
                    "access_scope": request.access_scope, "query_length": len(request.query)},
        )
        session.commit()
    except Exception:
        session.rollback()


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, session: Session = Depends(get_db),
         current_user: User | None = Depends(get_optional_current_user)) -> QueryResponse:
    try:
        replayed = replay_request(session, request)
        if replayed is not None:
            return replayed
    except GovernanceConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    preflight = run_preflight(request.query, request.access_scope)
    if preflight.decision != "ALLOW":
        _audit_preflight_denial(session, request, preflight, current_user)
        return _preflight_response(request, preflight)

    try:
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
        return govern_response(session, request, state,
                              requester_user_id=current_user.id if current_user else None)
    except GovernanceConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
