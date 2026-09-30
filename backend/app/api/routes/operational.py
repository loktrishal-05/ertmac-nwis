"""Authenticated operational services reuse /query governance and audit."""
from typing import Literal
from fastapi import APIRouter, Body, Depends, Path, Query, Response
from app.services import ui_reads
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.db.models import User, OperatorNote
from app.schemas.operational import NoteInput, HandoverInput, ComplianceInput
from app.schemas.query import QueryRequest, QueryResponse
from app.schemas.verified_knowledge import GapDecision, GapSubmission
from app.api.routes.query import query as execute_query
from app.api.routes.verified_knowledge import transaction
from app.services import knowledge_gaps as gaps, operator_notes as notes
from app.services.verified_knowledge import authorize

router = APIRouter(tags=["operational-intelligence"])

@router.post("/operator-notes")
def create_note(payload: NoteInput, actor: User = Depends(get_current_user), session: Session = Depends(get_db)):
    return transaction(session, lambda: notes.create(session, payload, actor))

@router.get("/operator-notes")
def list_notes(equipment_tag: str = Query(min_length=1, max_length=100), actor: User = Depends(get_current_user), session: Session = Depends(get_db)):
    def run():
        authorize(session, actor)
        asset = notes.equipment(session, equipment_tag)
        rows = session.scalars(select(OperatorNote).where(OperatorNote.equipment_id == asset.id,
            OperatorNote.access_scope == "internal").order_by(OperatorNote.created_at.desc(), OperatorNote.id.desc()).limit(100)).all()
        return [notes.export(session, row) for row in rows]
    return transaction(session, run)

@router.post("/shift-handover", response_model=QueryResponse)
def shift_handover(payload: HandoverInput, actor: User = Depends(get_current_user), session: Session = Depends(get_db)):
    request = QueryRequest(query=f"Prepare shift handover for equipment {payload.equipment_tag}\nOPERATIONAL_CONTEXT=" + payload.model_dump_json())
    return transaction(session, lambda: execute_query(request, session, actor))

@router.post("/environmental-compliance", response_model=QueryResponse)
def environmental_compliance(payload: ComplianceInput, actor: User = Depends(get_current_user), session: Session = Depends(get_db)):
    request = QueryRequest(query="Check environmental compliance against documented local rules\nOPERATIONAL_CONTEXT=" + payload.model_dump_json())
    return transaction(session, lambda: execute_query(request, session, actor))

@router.get("/knowledge-gaps")
def knowledge_gaps(response: Response, status: Literal["OPEN", "UNDER_REVIEW", "RESOLVED", "DISMISSED"] | None = None,
                   paging: tuple = Depends(ui_reads.page),
                   actor: User = Depends(get_current_user), session: Session = Depends(get_db)):
    limit, offset = paging
    result = transaction(session, lambda: gaps.listing(session, actor, status, limit + 1, offset))
    response.headers["X-As-Of"] = ui_reads.now().isoformat()
    response.headers["X-Sample-Size"] = str(min(len(result), limit))
    response.headers["X-Has-More"] = str(len(result) > limit).lower()
    response.headers["X-Scan-Limit"] = "1000"
    return result[:limit]

@router.post("/knowledge-gaps")
def submit_gap(payload: GapSubmission, actor: User = Depends(get_current_user), session: Session = Depends(get_db)):
    return transaction(session, lambda: gaps.submit(session, payload, actor))

@router.post("/knowledge-gaps/{gap_id}/{operation}")
def decide_gap(operation: Literal["assign", "resolve", "dismiss"], payload: GapDecision = Body(),
               gap_id: str = Path(pattern=r"^[a-f0-9]{64}$"), actor: User = Depends(require_role("reviewer", "admin")),
               session: Session = Depends(get_db)):
    return transaction(session, lambda: gaps.transition(session, gap_id, payload, actor, operation))
