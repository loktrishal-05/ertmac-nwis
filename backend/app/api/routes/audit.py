"""Audit list placeholder; hash chaining is not implemented."""

from fastapi import APIRouter
from app.schemas.audit import AuditLogResponse

router = APIRouter(tags=["audit"])


@router.get("/audit/log", response_model=list[AuditLogResponse])
def audit_log() -> list[AuditLogResponse]:
    return []
