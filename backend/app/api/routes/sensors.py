"""Read-only sensor history/features and CSV ingestion. Observations, not diagnoses."""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import require_role
from app.schemas.structured import (
    SensorIngestRequest, StructuredIngestResponse, SensorReadingsResponse,
    SensorFeatureRequest, SensorFeatureResponse,
)
from app.services.ingestion import IngestionConflict
from app.services.sensor_data import ingest_sensor
from app.services.structured_queries import sensor_readings_query, sensor_latest, sensor_features_query

router = APIRouter(tags=["sensors"])
logger = logging.getLogger(__name__)


@router.post("/data/sensors/ingest", response_model=StructuredIngestResponse, dependencies=[Depends(require_role("admin"))])
def ingest_sensor_csv(request: SensorIngestRequest, session: Session = Depends(get_db)):
    try:
        return ingest_sensor(request, session)
    except IngestionConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        logger.error("Sensor ingestion failed: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Sensor ingestion unavailable; check PostgreSQL and the CSV source.") from error


@router.get("/sensors/readings", response_model=SensorReadingsResponse)
def get_sensor_readings(
    equipment_tag: str | None = None, sensor_tag: str | None = None, measurement: str | None = None,
    start: datetime | None = None, end: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    session: Session = Depends(get_db),
):
    try:
        results = sensor_readings_query(session, equipment_tag=equipment_tag, sensor_tag=sensor_tag,
                                         measurement=measurement, start=start, end=end, limit=limit)
        return SensorReadingsResponse(results=results)
    except Exception as error:
        logger.error("Sensor readings query failed: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Sensor readings unavailable; check PostgreSQL.") from error


@router.get("/sensors/latest", response_model=SensorReadingsResponse)
def get_latest_readings(equipment_tag: str, sensor_tag: str | None = None, session: Session = Depends(get_db)):
    try:
        results = sensor_latest(session, equipment_tag, sensor_tag)
        return SensorReadingsResponse(results=results)
    except Exception as error:
        logger.error("Latest sensor reading query failed: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Latest sensor reading unavailable; check PostgreSQL.") from error


@router.post("/sensors/features", response_model=SensorFeatureResponse)
def post_sensor_features(request: SensorFeatureRequest, session: Session = Depends(get_db)):
    try:
        return sensor_features_query(session, request, as_of=datetime.now(timezone.utc))
    except Exception as error:
        logger.error("Sensor feature computation failed: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Sensor feature computation unavailable; check PostgreSQL.") from error
