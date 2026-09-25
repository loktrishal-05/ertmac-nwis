"""Authenticated operational services reuse /query governance and audit."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.db.session import get_db
from app.db.models import User, OperatorNote
from app.db.models.agent_run_step import AgentRunStep
from app.db.models.agent_run import AgentRun
from app.schemas.operational import NoteInput, HandoverInput, ComplianceInput
from app.schemas.query import QueryRequest, QueryResponse
from app.api.routes.query import query as execute_query
from app.api.routes.verified_knowledge import transaction
from app.services import operator_notes as notes
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
            OperatorNote.access_scope == "internal").order_by(OperatorNote.created_at.desc()).limit(100)).all()
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
def knowledge_gaps(actor: User = Depends(get_current_user), session: Session = Depends(get_db)):
    def run():
        authorize(session, actor)
        rows = session.scalars(select(AgentRunStep).join(AgentRun).where(AgentRunStep.node_name == "execution_metadata")
            .order_by(AgentRun.created_at.desc(), AgentRunStep.id.desc()).limit(100)).all()
        unique = {}
        for row in rows:
            for gap in row.usage.get("execution", {}).get("knowledge_gaps", []):
                unique.setdefault(gap["gap_id"], {**gap, "run_id": str(row.run_id)})
        return list(unique.values())
    return transaction(session, run)
