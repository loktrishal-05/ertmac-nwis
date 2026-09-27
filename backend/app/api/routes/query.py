"""Validated specialist output enters the common Phase 5A/5B boundary.

Phase 5E's deterministic preflight (app.services.preflight) runs after replay
handling (an already-governed request_id must keep replaying its original
committed draft unchanged) but strictly BEFORE run_graph -- a REFUSE/CLARIFY
decision returns without ever invoking the LangGraph router or the model
gateway (docs/phase5e.md, "Zero-model-call behavior")."""
import logging
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.graph import GraphExecutionError, run_graph
from app.agents.tracing import record_run
from app.api.deps import require_role
from app.core.config import settings
from app.db.models import User
from app.db.session import get_db
from app.schemas.query import QueryRequest, QueryResponse
from app.services.audit import append_event
from app.services.model_gateway import ModelRuntimeError, ModelTimeoutError, ModelUnavailableError
from app.services.governance import GovernanceConflict, govern_response, replay_request
from app.services.preflight import PreflightResult, run_preflight
from app.services.verified_knowledge import lookup as lookup_verified_knowledge
from app.services.adaptive_execution import choose as choose_execution

from app.services.execution_observability import observe_query, attach, stage, record_routing, routing_snapshot
from app.services.model_routing import select_model, RiskSignals
from app.services.operational_intelligence import route_for
from app.services.verified_knowledge import authorize
from app.services.approval import DecisionNotAllowed

router = APIRouter(tags=["query"])

_PREFLIGHT_EVENT_TYPES = {
    "unsupported_access_scope": "PREFLIGHT_SCOPE_DENIED",
    "prompt_injection_detected": "PREFLIGHT_INJECTION_REFUSED",
    "unsafe_action_request": "PREFLIGHT_UNSAFE_ACTION_REFUSED",
    "out_of_scope": "PREFLIGHT_OUT_OF_SCOPE_REFUSED",
    "ambiguous_domain": "PREFLIGHT_CLARIFICATION_REQUIRED",
}


def _preflight_response(request: QueryRequest, preflight: PreflightResult) -> QueryResponse:
    from app.services.local_voice import language
    return QueryResponse(
        request_id=request.request_id or uuid4(), run_id=str(uuid4()), route=None,
        route_confidence=None, route_reasoning=None,
        agent_result={"schema": "S5", "output": preflight.refusal.model_dump(mode="json")},
        evidence=[], warnings=[], human_approval_required=False, action_class=None, timings={},
        governance_status="INFORMATIONAL", human_review_required=False, presentation="INFORMATIONAL",
        execution={"input_language": request.input_language, "input_channel": request.input_channel, "language": language(request.input_language)},
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
@observe_query
def query(request: QueryRequest, session: Session = Depends(get_db),
         current_user: User = Depends(require_role("requester", "reviewer", "admin"))) -> QueryResponse:
    operational = route_for(request.query)
    if operational or request.input_channel == "voice":
        try:
            authorize(session, current_user)
        except DecisionNotAllowed as error:
            raise HTTPException(403, str(error)) from error
    # Phase 5F M1: replay_request runs first ONLY to detect a genuine
    # request_id/content conflict (409) -- unaffected by preflight timing.
    # The cached draft it may return is deliberately NOT returned yet: a
    # stored governed draft (created before this repair, before Phase 5E
    # existed, or before a guardrail was tightened) must not let a replay
    # skip the CURRENT preflight boundary. run_preflight is evaluated fresh
    # on every request, cached or not, and only once it ALLOWS does a cached
    # draft get returned -- otherwise the deterministic refusal/clarification
    # wins even for a request_id with an existing stored draft.
    try:
        replayed = replay_request(session, request, requester_user_id=current_user.id)
    except GovernanceConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    preflight = run_preflight(request.query, request.access_scope)
    if preflight.decision != "ALLOW":
        _audit_preflight_denial(session, request, preflight, current_user)
        return _preflight_response(request, preflight)

    if replayed is not None:
        return replayed

    # Existing authentication dependency and all preflight gates have already run.
    lookup_started = time.perf_counter()
    try:
        verified_state, knowledge_meta = lookup_verified_knowledge(session, request, current_user)
    except Exception:
        # Registry/source outages never grant trust; the existing path remains available.
        session.rollback()
        verified_state, knowledge_meta = None, {"path": "EXISTING_AGENTIC_PATH", "fallback_reason": "registry_unavailable"}
    knowledge_meta.setdefault("latency_ms", (time.perf_counter() - lookup_started) * 1000)
    logging.getLogger(__name__).info("Knowledge path: %s", knowledge_meta)
    if verified_state is not None:
        knowledge_meta.update(selected_path="VERIFIED_FAST_PATH", selection_source="deterministic",
                              reason_code="verified_exact_match", model_call_count=0)
        attach(session, request, verified_state, knowledge_meta)
        response = govern_response(session, request, verified_state,
                                   requester_user_id=current_user.id)
        return response.model_copy(update={"knowledge_lookup": knowledge_meta}) if response.presentation == "INFORMATIONAL" else response

    try:
        if operational:
            adaptive_state, execution_meta = None, {"selected_path": "EXISTING_AGENTIC_PATH", "selection_source": "deterministic", "reason_code": operational}
        else:
            with stage("system1"):
                adaptive_state, execution_meta = choose_execution(session, request, current_user)
        knowledge_meta.update(execution_meta)
        knowledge_meta["path"] = execution_meta["selected_path"]
        if adaptive_state is None:
            record_routing(select_model(request.query, requested_path=execution_meta["selected_path"],
                signals=RiskSignals(evidence_required=True, missing_verified_knowledge=True)))
        if adaptive_state is not None:
            state = adaptive_state
        elif operational:
            state = run_graph(request.query, session=session, access_scope=request.access_scope, actor_id=str(current_user.id))
        elif execution_meta["selected_path"] == "MGS_PATH":
            try:
                state = run_graph(request.query, session=session, access_scope=request.access_scope, mgs=True)
            except (GraphExecutionError, ModelRuntimeError, ModelTimeoutError, ModelUnavailableError):
                session.rollback()
                knowledge_meta.update(selected_path="EXISTING_AGENTIC_PATH", selection_source="fallback",
                                      fallback_reason="mgs_retrieval_or_graph_failed")
                state = run_graph(request.query, session=session, access_scope=request.access_scope)
        elif execution_meta["selected_path"] == "HYBRID_RAG_PATH":
            try:
                state = run_graph(request.query, session=session, access_scope=request.access_scope, knowledge_only=True)
            except (GraphExecutionError, ModelRuntimeError, ModelTimeoutError, ModelUnavailableError):
                session.rollback()
                knowledge_meta.update(path="EXISTING_AGENTIC_PATH", selected_path="EXISTING_AGENTIC_PATH",
                    selection_source="fallback", fallback_reason="hybrid_execution_failed")
                state = run_graph(request.query, session=session, access_scope=request.access_scope)
        else:
            state = run_graph(request.query, session=session, access_scope=request.access_scope)
        if state.get("execution_fallback"):
            knowledge_meta.update(selected_path="HYBRID_RAG_PATH", selection_source="fallback",
                                  fallback_reason=state["execution_fallback"])
        knowledge_meta["path"] = knowledge_meta["selected_path"]
        attach(session, request, state, knowledge_meta)
        knowledge_meta["latency_ms"] = (time.perf_counter() - lookup_started) * 1000
        knowledge_meta["execution_model_call_count"] = state["execution"]["model_call_count"]
        logging.getLogger(__name__).info("Adaptive execution: %s", knowledge_meta)
    except GovernanceConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except GraphExecutionError as wrapped:
        session.rollback()
        try:
            wrapped.state["execution"] = routing_snapshot()
            record_run(session, wrapped.state, status="error", model=settings.primary_model,
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
        response = govern_response(session, request, state,
                                   requester_user_id=current_user.id)
        return response.model_copy(update={"knowledge_lookup": knowledge_meta}) if response.presentation == "INFORMATIONAL" else response
    except GovernanceConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
