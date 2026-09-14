"""Local PDF ingestion, confined to data/raw."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.document import IngestionResponse
from app.schemas.knowledge import IngestRequest
from app.services.ingestion import ingest, IngestionConflict

router = APIRouter(tags=["documents"])


@router.post("/documents/ingest", response_model=IngestionResponse)
def ingest_document(request: IngestRequest, session: Session = Depends(get_db)) -> IngestionResponse:
    try:
        return ingest(request, session)
    except IngestionConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        logging.getLogger(__name__).error("Ingestion dependency failure: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Ingestion unavailable; check PostgreSQL, Qdrant, PDF validity, and local model artifacts.") from error
