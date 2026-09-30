"""Read-only sensor history/features and CSV ingestion. Observations, not diagnoses."""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.models import Equipment, SensorReading
from app.services import ui_reads
from app.services.equipment_tags import normalize_equipment_tag
from app.db.session import get_db
from app.api.deps import require_role
from app.schemas.structured import (
    SensorIngestRequest, StructuredIngestResponse, SensorReadingsResponse,
    SensorFeatureRequest, SensorFeatureResponse,
)
from app.schemas.maintenance_sensor_intelligence import (
    SensorMaintenanceIntelligenceRequest, SensorMaintenanceIntelligenceResponse,
)
from app.services.ingestion import IngestionConflict
from app.services.maintenance_sensor_intelligence import analyze
from app.services.sensor_data import ingest_sensor
from app.services.structured_queries import sensor_readings_query, sensor_latest, sensor_features_query

router = APIRouter(tags=["sensors"])
logger = logging.getLogger(__name__)

@router.get("/equipment")
def equipment(q: str = Query("", max_length=100), paging: tuple = Depends(ui_reads.page),
              session: Session = Depends(get_db)):
    limit, offset = paging
    query = select(Equipment)
    if q:
        query = query.where(Equipment.equipment_tag.startswith(normalize_equipment_tag(q), autoescape=True))
    rows = session.scalars(query.order_by(Equipment.equipment_tag, Equipment.id).offset(offset).limit(limit + 1)).all()
    return ui_reads.envelope([{k: getattr(r, k) for k in ("id", "equipment_tag", "name", "equipment_type", "location")}
                              for r in rows], limit, offset)

@router.get("/sensors/channels")
def channels(equipment_tag: str = Query(min_length=1, max_length=100), paging: tuple = Depends(ui_reads.page),
             session: Session = Depends(get_db)):
    limit, offset = paging
    rows = session.execute(select(SensorReading.sensor_tag, SensorReading.sensor_type, SensorReading.unit)
        .join(Equipment, Equipment.id == SensorReading.equipment_id)
        .where(Equipment.equipment_tag == normalize_equipment_tag(equipment_tag))
        .distinct().order_by(SensorReading.sensor_tag, SensorReading.sensor_type, SensorReading.unit)
        .offset(offset).limit(limit + 1)).all()
    return ui_reads.envelope([{"sensor_tag": r.sensor_tag, "measurement": r.sensor_type, "unit": r.unit,
                               "thresholds": None} for r in rows], limit, offset)



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
    equipment_tag: str | None = Query(None, max_length=100), sensor_tag: str | None = Query(None, max_length=100), measurement: str | None = Query(None, max_length=100),
    start: datetime | None = None, end: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    session: Session = Depends(get_db),
):
    start, end = ui_reads.validate_range(start, end)
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


@router.post("/sensors/intelligence", response_model=SensorMaintenanceIntelligenceResponse)
def post_sensor_intelligence(request: SensorMaintenanceIntelligenceRequest, session: Session = Depends(get_db)):
    try:
        response, _refs = analyze(session, request)
        return response
    except Exception as error:
        logger.error("Sensor intelligence analysis failed: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Sensor intelligence analysis unavailable; check PostgreSQL.") from error
