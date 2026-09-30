"""Authenticated durable entry point for the existing LangGraph."""
from uuid import UUID
from datetime import datetime
from typing import Literal
from app.services import ui_reads

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.models import User
from app.db.session import get_db
from app.schemas.query import QueryRequest
from app.services import durable_execution as service
from app.services.execution_observability import observe_query
from app.services.governance import GovernanceConflict

router = APIRouter(prefix="/executions", tags=["executions"])
principal = require_role("requester", "reviewer", "admin")


def invoke(fn, *args):
    try:
        return fn(*args)
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    except (service.RecoveryConflict, GovernanceConflict) as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("")
@observe_query
def start(request: QueryRequest, session: Session = Depends(get_db), actor: User = Depends(principal)):
    return invoke(service.start, session, request, actor)


@router.get("")
def listing(paging: tuple = Depends(ui_reads.page),
            status: Literal["PENDING", "RUNNING", "WAITING_APPROVAL", "COMPLETED", "REJECTED", "INTERRUPTED", "FAILED"] | None = None,
            start: datetime | None = None, end: datetime | None = None,
            session: Session = Depends(get_db), actor: User = Depends(principal)):
    return ui_reads.execution_list(session, actor, *paging, status, start, end)


@router.get("/{execution_id}")
def status(execution_id: UUID, paging: tuple = Depends(ui_reads.page),
           session: Session = Depends(get_db), actor: User = Depends(principal)):
    return invoke(ui_reads.execution_detail, session, execution_id, actor, *paging)


@router.post("/{execution_id}/resume")
@observe_query
def resume(execution_id: UUID, session: Session = Depends(get_db), actor: User = Depends(principal)):
    return invoke(service.resume, session, execution_id, actor)
