"""Local P&ID OCR preparation; no retrieval or process reasoning."""
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.pid import PIDProcessRequest, PIDProcessResponse
from app.services.ingestion import IngestionConflict
from app.services.pid_processing import process_pid
from app.services.pid_indexing import index_pid

router = APIRouter(tags=["documents"])


@router.post("/documents/pid/{version_id}/index")
def index_drawing(version_id: UUID, session: Session = Depends(get_db)):
    try:
        return index_pid(version_id, session)
    except IngestionConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        logging.getLogger(__name__).error("P&ID indexing failed: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="P&ID indexing unavailable; check local models and retrieval services.") from error


@router.post("/documents/pid/process", response_model=PIDProcessResponse)
def process_drawing(request: PIDProcessRequest, session: Session = Depends(get_db)):
    try:
        return process_pid(request, session)
    except IngestionConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        logging.getLogger(__name__).error("P&ID processing failed: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Local P&ID OCR unavailable; check PostgreSQL and PP-OCRv5 artifacts/runtime.") from error
