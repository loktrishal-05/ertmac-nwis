"""Retrieval routes; no LLM answering."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.knowledge import RetrieveRequest, RetrieveResponse
from app.services.retrieval import retrieve

router = APIRouter(tags=["knowledge"])
logger = logging.getLogger(__name__)


@router.post("/knowledge/retrieve", response_model=RetrieveResponse)
def retrieve_evidence(request: RetrieveRequest, session: Session = Depends(get_db)):
    try:
        return retrieve(request, session)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        logger.error("Retrieval dependency failure: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Retrieval unavailable; check PostgreSQL, Qdrant, and local model artifacts.") from error
