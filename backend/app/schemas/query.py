"""Query contract: POST /query classifies the request via the Phase 4B
router graph and returns the route decision, any evidence gathered, and
per-step timings. No route beyond routing itself reasons yet — agent_result
is a stub-node placeholder ({"status": "not_implemented", ...}) on every
route in this phase.

extra='forbid' on the request rejects any attempt to route
model/runtime/base_url/temperature through this endpoint: those are operator
configuration (app.core.config), never a per-request override."""
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.agents.evidence import EvidenceRef


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
    access_scope: str = Field(default="internal", min_length=1, max_length=50)


class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    route: str | None
    route_confidence: float | None
    route_reasoning: str | None
    agent_result: dict | None
    evidence: list[EvidenceRef]
    warnings: list[str]
    human_approval_required: bool
    action_class: str | None
    timings: dict
