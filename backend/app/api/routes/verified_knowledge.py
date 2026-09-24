"""Authenticated registry; decisions reuse the Phase 5 approval ledger."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_role
from app.db.models import User, VerifiedKnowledge
from app.db.session import get_db
from app.schemas.verified_knowledge import KnowledgeCandidate, KnowledgeDecision
from app.services import verified_knowledge as service
from app.services.approval import DecisionConflict, DecisionNotAllowed
from app.services.governance import ReleaseNotAllowed

router = APIRouter(prefix="/verified-knowledge", tags=["verified-knowledge"])


def transaction(session, fn):
    try:
        result = fn()
        session.commit()
        return result
    except (DecisionNotAllowed, ReleaseNotAllowed) as error:
        session.rollback()
        raise HTTPException(403, str(error)) from error
    except (service.KnowledgeConflict, DecisionConflict) as error:
        session.rollback()
        raise HTTPException(409, str(error)) from error
    except Exception:
        session.rollback()
        raise


@router.post("")
def create(payload: KnowledgeCandidate, user: User = Depends(get_current_user), session: Session = Depends(get_db)):
    return transaction(session, lambda: service.export_item(service.create_candidate(session, payload, user)))


@router.get("")
def listing(q: str = Query(default="", max_length=2000), user: User = Depends(get_current_user), session: Session = Depends(get_db)):
    def run():
        service.authorize(session, user)
        query = select(VerifiedKnowledge.id).where(VerifiedKnowledge.access_scope == "internal")
        if q:
            query = query.where(VerifiedKnowledge.match_key == service.canonical_hash(service.normalized(q)))
        ids = session.scalars(query.order_by(VerifiedKnowledge.created_at.desc()).limit(100)).all()
        return [service.export_item(service.inspect_item(session, i, user)) for i in ids]
    return transaction(session, run)


@router.get("/{knowledge_id}")
def inspect(knowledge_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_db)):
    return transaction(session, lambda: service.export_item(service.inspect_item(session, knowledge_id, user)))


@router.post("/{knowledge_id}/{operation}")
def decide(knowledge_id: UUID, operation: str, payload: KnowledgeDecision,
           user: User = Depends(require_role("reviewer", "admin")), session: Session = Depends(get_db)):
    return transaction(session, lambda: service.export_item(service.decide(session, knowledge_id, payload, user, operation)))
