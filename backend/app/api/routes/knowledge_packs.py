"""Authenticated bounded-pack management and read-only execution inspection."""
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_role
from app.api.routes.verified_knowledge import transaction
from app.db.models import KnowledgePack, User
from app.db.session import get_db
from app.schemas.query import QueryRequest
from app.schemas.verified_knowledge import KnowledgeDecision
from app.services import knowledge_packs as packs
from app.services import verified_knowledge as verified
from app.services.adaptive_execution import strategy
from app.services.preflight import run_preflight

router = APIRouter(tags=["knowledge-packs"])

@router.post("/knowledge-packs")
def create(payload: packs.PackCandidate, user: User = Depends(get_current_user), session: Session = Depends(get_db)):
    def run():
        pack = packs.create(session, payload, user)
        return packs.export(*packs.inspect(session, pack.id, user))
    return transaction(session, run)

@router.get("/knowledge-packs")
def listing(user: User = Depends(get_current_user), session: Session = Depends(get_db)):
    def run():
        verified.authorize(session, user)
        ids = session.scalars(select(KnowledgePack.id).order_by(KnowledgePack.created_at.desc()).limit(100)).all()
        return [packs.export(*packs.inspect(session, i, user)) for i in ids]
    return transaction(session, run)

@router.get("/knowledge-packs/{pack_id}")
def inspect(pack_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_db)):
    return transaction(session, lambda: packs.export(*packs.inspect(session, pack_id, user)))

@router.post("/knowledge-packs/{pack_id}/{operation}")
def decide(pack_id: UUID, operation: str, payload: KnowledgeDecision,
           user: User = Depends(require_role("reviewer", "admin")), session: Session = Depends(get_db)):
    return transaction(session, lambda: packs.export(*packs.decide(session, pack_id, payload, user, operation)))

@router.post("/execution/inspect")
def inspect_execution(request: QueryRequest, user: User = Depends(get_current_user), session: Session = Depends(get_db)):
    verified.authorize(session, user)
    preflight = run_preflight(request.query, request.access_scope)
    # Pure preview: no inference, pack serving, approval or release side effect.
    return {"preflight_decision": preflight.decision, "reason_code": preflight.reason_code,
            "deterministic_path_after_verified_and_pack_miss": strategy(request.query) if preflight.decision == "ALLOW" else None,
            "preview_only": True}
