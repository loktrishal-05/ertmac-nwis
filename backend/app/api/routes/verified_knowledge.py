"""Authenticated registry; decisions reuse the Phase 5 approval ledger."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from app.services import ui_reads
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
def listing(response: Response, q: str = Query(default="", max_length=2000),
            status: Literal["CANDIDATE", "VERIFIED", "STALE", "REVOKED"] | None = None,
            origin: str | None = Query(default=None, max_length=40),
            equipment_tag: str | None = Query(default=None, max_length=100),
            paging: tuple = Depends(ui_reads.page),
            user: User = Depends(get_current_user), session: Session = Depends(get_db)):
    def run():
        service.authorize(session, user)
        query = select(VerifiedKnowledge.id).where(VerifiedKnowledge.access_scope == "internal")
        if q:
            query = query.where(VerifiedKnowledge.match_key == service.canonical_hash(service.normalized(q)))
        if origin:
            query = query.where(VerifiedKnowledge.origin == origin)
        limit, offset = paging
        # Scan stable creation order: refresh may change status, so it cannot define the offset set.
        ids = session.scalars(query.order_by(VerifiedKnowledge.created_at.desc(), VerifiedKnowledge.id.desc())
                              .offset(offset).limit(101)).all()
        result, scanned = [], 0
        for ident in ids[:100]:
            item = service.inspect_item(session, ident, user)
            scanned += 1
            if (status is None or item.status == status) and (
                    equipment_tag is None or equipment_tag in (item.asset_scope or {}).get("equipment_tags", [])):
                result.append(service.export_item(item))
            if len(result) == limit:
                break
        more = scanned < len(ids)
        response.headers["X-As-Of"] = ui_reads.now().isoformat()
        response.headers["X-Sample-Size"] = str(len(result))
        response.headers["X-Has-More"] = str(more).lower()
        response.headers["X-Scan-Limit"] = "100"
        if more:
            response.headers["X-Next-Offset"] = str(offset + scanned)
        return result
    return transaction(session, run)


@router.post("/revalidate")
def revalidate(document_id: UUID | None = None, user: User = Depends(require_role("reviewer", "admin")),
               session: Session = Depends(get_db)):
    return transaction(session, lambda: [service.export_item(i) for i in service.revalidate(session, user, document_id)])


@router.get("/{knowledge_id}")
def inspect(knowledge_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_db)):
    return transaction(session, lambda: service.export_item(service.inspect_item(session, knowledge_id, user)))


@router.get("/{knowledge_id}/history")
def history(knowledge_id: UUID, user: User = Depends(require_role("reviewer", "admin")), session: Session = Depends(get_db)):
    return transaction(session, lambda: service.history(session, knowledge_id, user))


@router.post("/{knowledge_id}/{operation}")
def decide(knowledge_id: UUID, operation: str, payload: KnowledgeDecision,
           user: User = Depends(require_role("reviewer", "admin")), session: Session = Depends(get_db)):
    return transaction(session, lambda: service.export_item(service.decide(session, knowledge_id, payload, user, operation)))
