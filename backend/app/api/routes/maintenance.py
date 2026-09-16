"""Read-only maintenance history and CSV ingestion; no diagnostic inference."""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.structured import MaintenanceIngestRequest, StructuredIngestResponse, MaintenanceHistoryResponse
from app.services.ingestion import IngestionConflict
from app.services.maintenance_data import ingest_maintenance
from app.services.structured_queries import maintenance_history, work_order_lookup

router = APIRouter(tags=["maintenance"])
logger = logging.getLogger(__name__)


@router.post("/data/maintenance/ingest", response_model=StructuredIngestResponse)
def ingest_maintenance_csv(request: MaintenanceIngestRequest, session: Session = Depends(get_db)):
    try:
        return ingest_maintenance(request, session)
    except IngestionConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        logger.error("Maintenance ingestion failed: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Maintenance ingestion unavailable; check PostgreSQL and the CSV source.") from error


@router.get("/maintenance/history", response_model=MaintenanceHistoryResponse)
def get_maintenance_history(
    equipment_tag: str | None = None, work_order_id: str | None = None,
    maintenance_type: str | None = None, status: str | None = None,
    start: datetime | None = None, end: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=2000),
    session: Session = Depends(get_db),
):
    try:
        results = maintenance_history(session, equipment_tag=equipment_tag, work_order_id=work_order_id,
                                       maintenance_type=maintenance_type, status=status, start=start, end=end, limit=limit)
        return MaintenanceHistoryResponse(results=results)
    except Exception as error:
        logger.error("Maintenance history query failed: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Maintenance history unavailable; check PostgreSQL.") from error


@router.get("/maintenance/work-orders/{work_order_id}", response_model=MaintenanceHistoryResponse)
def get_work_order(work_order_id: str, session: Session = Depends(get_db)):
    try:
        results = work_order_lookup(session, work_order_id)
        return MaintenanceHistoryResponse(results=results)
    except Exception as error:
        logger.error("Work order lookup failed: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Work order lookup unavailable; check PostgreSQL.") from error
