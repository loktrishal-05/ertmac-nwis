"""Human-submitted candidates cannot supply trust, reviewer, hashes, scope or evidence text."""
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

# Where a candidate or gap came from. Descriptive provenance only; never trust.
Origin = Literal["manual_submission", "document_ingestion", "operator_note", "maintenance_analysis",
                 "pid_evidence", "knowledge_gap", "query_execution"]
Reference = Field(default=None, max_length=200, pattern=r"^[A-Za-z0-9:_.-]+$")

class KnowledgeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=2000)
    statement: str = Field(min_length=1, max_length=6000)
    chunk_ids: list[UUID] = Field(min_length=1, max_length=10)
    access_scope: Literal["internal"] = "internal"
    supersedes_id: UUID | None = None
    origin: Origin = "manual_submission"
    origin_reference: str | None = Reference

class KnowledgeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    comment: str = Field(min_length=1, max_length=1000)

class GapSubmission(BaseModel):
    """No status, scope, reviewer or resolution fields: the server owns all of them."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    subject: str = Field(min_length=1, max_length=200)
    gap_type: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    required_evidence: str = Field(min_length=1, max_length=1000)
    related_evidence: list[str] = Field(default_factory=list, max_length=20)
    origin: Origin = "manual_submission"
    origin_reference: str | None = Reference

class GapDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str = Field(min_length=1, max_length=1000)
    assignee_id: UUID | None = None
    knowledge_id: UUID | None = None
    document_version_id: UUID | None = None
