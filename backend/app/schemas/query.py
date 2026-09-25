"""Query contract: validated specialist results pass the Phase 5A boundary.
Governed results are persisted drafts, never approved or released actions.

extra='forbid' on the request rejects any attempt to route
model/runtime/base_url/temperature through this endpoint: those are operator
configuration (app.core.config), never a per-request override."""
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.agents.evidence import EvidenceRef


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
    access_scope: str = Field(default="internal", min_length=1, max_length=50)
    request_id: UUID | None = Field(default=None, description="Optional idempotency key for governed requests; not identity or authorization")
    requester_reference: str | None = Field(default=None, max_length=255, description="Claimed provenance only; never an authenticated principal")


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
    request_id: UUID
    governance_status: Literal["INFORMATIONAL", "PENDING_REVIEW", "APPROVED", "REJECTED", "REVOKED", "EXPIRED"]
    action_revision_id: UUID | None = None
    human_review_required: bool
    presentation: Literal["INFORMATIONAL", "DRAFT"]
    canonicalization_version: str | None = None
    canonical_request_hash: str | None = None
    canonical_proposal_hash: str | None = None
    evidence_binding_status: Literal["PENDING_INTEGRITY", "VERIFIED", "FAILED", "LEGACY_UNVERIFIED"] | None = None
    policy_version: str | None = None

    knowledge_lookup: dict | None = None
    execution: dict | None = None
