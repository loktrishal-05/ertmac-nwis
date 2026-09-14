"""Approval contracts; no review logic is implemented."""

from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict


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
