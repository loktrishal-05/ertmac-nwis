"""WorkbenchState: the LangGraph state contract. A TypedDict (LangGraph
requires this, not a Pydantic model), but every value placed into it is
either a validated Pydantic instance or a primitive.

Accumulating fields use Annotated[list[X], operator.add] reducers. Without a
reducer, a node returning {"warnings": [...]} would silently REPLACE prior
warnings instead of appending — exactly how an early safety warning could
vanish before the response is assembled.

State carries EvidenceRef objects, not raw document text beyond what a
variant already stores (e.g. a chunk's own quote). No node accumulates a
second copy of retrieved text into a separate field.

human_approval_required and action_class are recorded fields, written by
nothing in Phase 4B. Phase 5 enforces them; this phase does not build a gate.

step_records is additive beyond the prompt's minimum field list: it is what
makes per-node timings/usage traceable (see tracing.py) even though
tool_invocations is legitimately always empty in Phase 4B (stub nodes never
call a tool)."""
import operator
from typing import Annotated, TypedDict

from pydantic import BaseModel, ConfigDict

from app.agents.evidence import EvidenceRef


def _or_bool(previous: bool | None, current: bool | None) -> bool:
    """Approval requirement is monotonic within a graph run.

    Phase 4 records an advisory requirement only; Phase 5 will enforce the
    actual approval boundary.  Keeping this reducer monotonic prevents a
    later node or model-shaped update from clearing a requirement already
    established by deterministic policy.
    """
    return bool(previous) or bool(current)


def _strongest_action_class(previous: str | None, current: str | None) -> str | None:
    order = {"shutdown": 0, "isolation": 1, "process_change": 2, "inspection": 3, "informational": 4}
    if previous is None:
        return current
    if current is None:
        return previous
    return previous if order.get(previous, 99) <= order.get(current, 99) else current


class ToolInvocationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str
    arguments: dict
    evidence_ids: list[str]
    duration_ms: float
    warnings: list[str] = []
    error: str | None = None


class WorkbenchState(TypedDict):
    run_id: str
    query: str
    access_scope: str
    route: str | None
    route_confidence: float | None
    route_reasoning: str | None
    evidence: Annotated[list[EvidenceRef], operator.add]
    tool_invocations: Annotated[list[ToolInvocationRecord], operator.add]
    agent_result: dict | None
    warnings: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
    human_approval_required: Annotated[bool, _or_bool]
    action_class: Annotated[str | None, _strongest_action_class]
    started_at: str
    finished_at: str | None
    step_records: Annotated[list[dict], operator.add]
    gateway_repair_attempts: int
