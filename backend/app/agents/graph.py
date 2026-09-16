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

from app.agents.nodes.router import router_node
from app.agents.nodes.stubs import make_stub_node
from app.agents.prompts.router import ROUTE_NAMES
from app.agents.state import WorkbenchState
from app.core.config import settings
from app.services.model_gateway import get_model_gateway


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
        update = dict(fn(state))
        usage = update.pop("_usage", {})
        timings = update.pop("_timings", {})
        finished_at = _now()
        duration_ms = (perf_counter() - started) * 1000
        step = {
            "node_name": node_name, "started_at": started_at, "finished_at": finished_at,
            "duration_ms": duration_ms, "tool_name": None,
            "evidence_ids": [ref.evidence_id for ref in update.get("evidence", [])],
            "usage": usage, "timings": timings, "warnings": update.get("warnings", []), "error": None,
        }
        update["step_records"] = [step]
        return update
    _wrapped.__name__ = f"traced_{node_name}"
    return _wrapped


def _route_selector(state) -> str:
    route = state.get("route")
    return route if route in ROUTE_NAMES else "clarification"


def build_graph():
    gateway = get_model_gateway()
    builder = StateGraph(WorkbenchState)
    builder.add_node("router", _traced("router", lambda state: router_node(state, gateway=gateway)))
    for route in ROUTE_NAMES:
        builder.add_node(route, _traced(route, make_stub_node(route)))
    builder.add_edge(START, "router")
    builder.add_conditional_edges("router", _route_selector, {route: route for route in ROUTE_NAMES})
    for route in ROUTE_NAMES:
        builder.add_edge(route, END)
    return builder.compile()


@lru_cache(maxsize=1)
def get_graph():
    return build_graph()


def run_graph(query: str) -> WorkbenchState:
    graph = get_graph()
    initial_state: WorkbenchState = {
        "run_id": str(uuid4()), "query": query, "route": None, "route_confidence": None,
        "route_reasoning": None, "evidence": [], "tool_invocations": [], "agent_result": None,
        "warnings": [], "errors": [], "human_approval_required": False, "action_class": None,
        "started_at": _now(), "finished_at": None, "step_records": [],
    }
    result = graph.invoke(initial_state, config={"recursion_limit": settings.agent_max_steps})
    result["finished_at"] = _now()
    return result
