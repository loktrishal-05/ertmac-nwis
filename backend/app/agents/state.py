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
    route: str | None
    route_confidence: float | None
    route_reasoning: str | None
    evidence: Annotated[list[EvidenceRef], operator.add]
    tool_invocations: Annotated[list[ToolInvocationRecord], operator.add]
    agent_result: dict | None
    warnings: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
    human_approval_required: bool
    action_class: str | None
    started_at: str
    finished_at: str | None
    step_records: Annotated[list[dict], operator.add]
