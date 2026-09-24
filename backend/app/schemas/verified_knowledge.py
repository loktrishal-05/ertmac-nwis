"""Human-submitted candidates cannot supply trust, reviewer, hashes or evidence text."""
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class KnowledgeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=2000)
    statement: str = Field(min_length=1, max_length=6000)
    chunk_ids: list[UUID] = Field(min_length=1, max_length=10)
    access_scope: Literal["internal"] = "internal"
    supersedes_id: UUID | None = None

class KnowledgeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    comment: str = Field(min_length=1, max_length=1000)
