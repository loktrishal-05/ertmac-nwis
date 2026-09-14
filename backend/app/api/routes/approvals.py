"""Approval placeholders; no records are read or mutated."""

from uuid import UUID
from fastapi import APIRouter
from app.schemas.approval import ApprovalResponse, ApprovalPlaceholder

router = APIRouter(tags=["approvals"])


@router.get("/approvals", response_model=list[ApprovalResponse])
def list_approvals() -> list[ApprovalResponse]:
    return []


@router.post("/approvals/{approval_id}", response_model=ApprovalPlaceholder)
def review_approval(approval_id: UUID) -> ApprovalPlaceholder:
    return ApprovalPlaceholder()
