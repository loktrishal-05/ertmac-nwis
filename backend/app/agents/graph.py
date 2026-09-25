"""Graph construction and invocation.

Synchronous: the Phase 4A gateway is sync and every existing FastAPI handler
and service in this repository is sync. graph.invoke(), never ainvoke() —
introducing one async layer into an otherwise sync stack buys nothing and
risks a blocking call inside an event loop somewhere.

No checkpointer in 4B: runs are single-shot, and app/agents/tracing.py's own
tables are the auditable record — they must not be conflated with LangGraph's
own (unused) persistence mechanism.

Built once behind the same lazy-singleton pattern as get_model_gateway()."""
from datetime import datetime, timezone
from functools import lru_cache
from time import perf_counter
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from app.agents.nodes.knowledge import knowledge_node
from app.agents.nodes.maintenance import maintenance_node
from app.agents.nodes.optimization import optimization_node
from app.agents.nodes.router import router_node
from app.agents.nodes.safety import safety_node
from app.agents.nodes.stubs import make_stub_node
from app.agents.nodes.terminal import clarification_node, guardrail_refusal_node
from app.agents.prompts.router import ROUTE_NAMES
from app.agents.state import WorkbenchState
from app.core.config import settings
from app.services.model_gateway import get_model_gateway
from app.agents.context import (reset_access_scope, set_access_scope, reset_deadline, set_deadline,
                                reset_tool_records, set_tool_records, tool_records)
from app.agents.context import gateway_repairs, reset_gateway_repairs, set_gateway_repairs


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _traced(node_name: str, fn):
    """Wraps a node function so every execution produces exactly one
    step_records entry, whether or not the node made a gateway call. A node
    may optionally return transient "_usage"/"_timings" keys (see
    nodes/router.py) to attach gateway usage/timings to its own step; the
    wrapper strips them before the update reaches WorkbenchState, since
    neither key is part of the state contract."""
    def _wrapped(state):
        started = perf_counter()
        started_at = _now()
        tools_before = len(tool_records())
        update = dict(fn(state))
        # Nested specialist outputs are advisory, but a true requirement is
        # still a requirement.  Mirror it at graph state for every route.
        result = update.get("agent_result") or {}
        output = result.get("output") if isinstance(result, dict) else None
        if isinstance(output, dict) and output.get("human_approval_required") is True:
            update["human_approval_required"] = True
        usage = update.pop("_usage", {})
        timings = update.pop("_timings", {})
        finished_at = _now()
        duration_ms = (perf_counter() - started) * 1000
        tool_delta = tool_records()[tools_before:]
        if tool_delta:
            timings = {**timings, "tools": [
                {key: tool.get(key) for key in ("tool_name", "duration_ms", "evidence_ids")}
                for tool in tool_delta
            ]}
        step = {
            "node_name": node_name, "started_at": started_at, "finished_at": finished_at,
            "duration_ms": duration_ms, "tool_name": tool_delta[0].get("tool_name") if len(tool_delta) == 1 else None,
            "evidence_ids": [ref.evidence_id for ref in update.get("evidence", [])],
            "usage": usage, "timings": timings, "warnings": update.get("warnings", []), "error": None,
        }
        if tool_delta:
            update["tool_invocations"] = tool_delta
        update["step_records"] = [step]
        return update
    _wrapped.__name__ = f"traced_{node_name}"
    return _wrapped


def _route_selector(state) -> str:
    route = state.get("route")
    return route if route in ROUTE_NAMES else "clarification"


class GraphExecutionError(RuntimeError):
    """Carries partial state so failed runs can still be traced."""
    def __init__(self, original: Exception, state: WorkbenchState):
        super().__init__(str(original))
        self.original = original
        self.state = state


def build_graph(session=None, *, knowledge_only=False):
    """session=None preserves 4B's exact behaviour (every route a stub; no DB
    access). Phase 4C/4D's real nodes need a per-request SQLAlchemy session
    for their read-only tool calls, which a process-wide cached singleton
    graph cannot hold (a session is request-scoped, not process-scoped) -- so
    a node that needs one is bound to it via closure at build time here, and
    run_graph() below builds a fresh graph per call once a session is
    supplied rather than reusing get_graph()'s cache. See
    docs/phase4-decisions.md D-008 for the alternatives considered."""
    gateway = get_model_gateway()
    builder = StateGraph(WorkbenchState)
    if knowledge_only:
        builder.add_node("knowledge", _traced("knowledge", lambda state: knowledge_node(state, gateway=gateway, session=session)))
        builder.add_edge(START, "knowledge")
        builder.add_edge("knowledge", END)
        return builder.compile()
    builder.add_node("router", _traced("router", lambda state: router_node(state, gateway=gateway)))
    route_nodes = {
        "knowledge": lambda state: knowledge_node(state, gateway=gateway, session=session),
        "maintenance": lambda state: maintenance_node(state, gateway=gateway, session=session),
        "safety": lambda state: safety_node(state, gateway=gateway, session=session),
        "combined_safety_maintenance": lambda state: safety_node(state, gateway=gateway, session=session),
        "process_optimization": lambda state: optimization_node(state, gateway=gateway, session=session),
        "guardrail_refusal": guardrail_refusal_node,
        "clarification": clarification_node,
    }
    for route in ROUTE_NAMES:
        builder.add_node(route, _traced(route, route_nodes.get(route, make_stub_node(route))))
    builder.add_edge(START, "router")
    builder.add_conditional_edges("router", _route_selector, {route: route for route in ROUTE_NAMES})
    for route in ROUTE_NAMES:
        builder.add_edge(route, END)
    return builder.compile()


@lru_cache(maxsize=1)
def get_graph():
    return build_graph()


def run_graph(query: str, *, session=None, access_scope: str = "internal", knowledge_only: bool = False) -> WorkbenchState:
    scope_token = set_access_scope(access_scope)
    deadline_token = set_deadline(settings.agent_run_timeout_seconds)
    records_token = set_tool_records([])
    repairs_token = set_gateway_repairs([0])
    graph = build_graph(session=session, knowledge_only=True) if knowledge_only else (get_graph() if session is None else build_graph(session=session))
    initial_state: WorkbenchState = {
        "run_id": str(uuid4()), "query": query, "access_scope": access_scope or "internal", "route": "knowledge" if knowledge_only else None, "route_confidence": None,
        "route_reasoning": None, "evidence": [], "tool_invocations": [], "agent_result": None,
        "warnings": [], "errors": [], "human_approval_required": False, "action_class": None,
        "started_at": _now(), "finished_at": None, "step_records": [],
        "gateway_repair_attempts": 0,
    }
    try:
        result = graph.invoke(initial_state, config={"recursion_limit": settings.agent_max_steps})
        result["tool_invocations"] = tool_records()
        result["gateway_repair_attempts"] = gateway_repairs()
        result["finished_at"] = _now()
        return result
    except Exception as error:
        partial = dict(initial_state)
        partial["finished_at"] = _now()
        partial["errors"] = [str(error)]
        partial["tool_invocations"] = tool_records()
        partial["gateway_repair_attempts"] = gateway_repairs()
        raise GraphExecutionError(error, partial) from error
    finally:
        reset_access_scope(scope_token)
        reset_deadline(deadline_token)
        reset_tool_records(records_token)
        reset_gateway_repairs(repairs_token)
