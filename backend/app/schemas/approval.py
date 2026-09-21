"""Approval contracts.

ApprovalResponse/ApprovalPlaceholder are the untouched legacy Phase 2
placeholder shapes -- retained for the inert legacy route only; they carry no
Phase 5B authority (see docs/phase5b.md, "legacy Approval handling"). The
Phase 5B schemas below (PendingRevisionSummary onward) back the real
authenticated approval workflow.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    action_id: UUID
    status: str
    requested_by: UUID
    reviewed_by: UUID | None
    reviewer_comment: str | None
    created_at: datetime
    reviewed_at: datetime | None


class ApprovalPlaceholder(BaseModel):
    status: Literal["not_implemented"] = "not_implemented"
    message: str = "Approval workflow will be implemented in a later phase."


class PendingRevisionSummary(BaseModel):
    action_revision_id: UUID
    request_id: UUID
    route: str | None
    created_at: datetime
    requester_user_id: UUID | None


class DecisionRecord(BaseModel):
    decision_id: UUID
    approver_id: UUID
    decision: str
    decided_at: datetime
    reviewer_comment: str | None
    expires_at: datetime | None
    revoked_decision_id: UUID | None


class EvidenceItemSummary(BaseModel):
    item_index: int
    evidence_type: str
    evidence_id: str
    source_identifier: str
    canonical_item_hash: str


class RevisionDetail(BaseModel):
    action_revision_id: UUID
    request_id: UUID
    action_id: UUID
    governance_status: str
    route: str | None
    agent_result: dict | None
    evidence: list[dict]
    warnings: list[str]
    canonical_request_hash: str
    canonical_proposal_hash: str
    evidence_binding_status: str
    evidence_manifest_id: UUID | None = None
    evidence_manifest_hash: str | None = None
    evidence_item_summaries: list[EvidenceItemSummary] = []
    policy_version: str
    requester_user_id: UUID | None
    decisions: list[DecisionRecord]


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject", "revoke"]
    reviewer_comment: str | None = Field(default=None, max_length=2000)
    # Optimistic-binding safety net only: the server always re-derives the
    # authoritative revision/hash from the path parameter and the database:
    # this can only make a decision fail (mismatch), never grant one.
    expected_revision_id: UUID | None = None


class DecisionResult(BaseModel):
    decision_id: UUID
    action_revision_id: UUID
    decision: str
    governance_status: str
    decided_at: datetime


class ReleaseResult(RevisionDetail):
    released_at: datetime
