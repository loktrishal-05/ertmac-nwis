"""Bounded read-only maintenance/sensor queries."""
from uuid import uuid4

from sqlalchemy import select, case, func

from app.core.config import settings
from app.db.models.equipment import Equipment
from app.db.models.maintenance_record import MaintenanceRecord
from app.db.models.sensor_reading import SensorReading
from app.schemas.structured import (
    MaintenanceRecordOut, SensorReadingOut, StructuredCitation, SensorFeatureResponse,
)
from app.services.equipment_tags import normalize_equipment_tag
from app.services.ingestion import write_json
from app.services.sensor_features import compute_features, detect_anomalies


def maintenance_out(record, equipment_tag) -> MaintenanceRecordOut:
    return MaintenanceRecordOut(
        id=record.id, equipment_tag=equipment_tag, raw_equipment_tag=record.raw_equipment_tag,
        work_order_id=record.work_order_id, maintenance_type=record.maintenance_type,
        failure_mode=record.failure_mode, maintenance_date=record.maintenance_date,
        description=record.description, downtime_hours=record.downtime_hours,
        parts_replaced=record.parts_replaced, technician_notes=record.technician_notes,
        status=record.status, ingested_at=record.created_at,
        citation=StructuredCitation(source_filename=record.source_filename,
                                     source_sha256=record.source_sha256,
                                     source_row_number=record.source_row_number),
    )


def sensor_out(reading, equipment_tag) -> SensorReadingOut:
    return SensorReadingOut(
        id=reading.id, equipment_tag=equipment_tag, sensor_tag=reading.sensor_tag,
        measurement=reading.sensor_type, value=reading.value, unit=reading.unit,
        quality=reading.quality, timestamp=reading.timestamp, ingested_at=reading.created_at,
        citation=StructuredCitation(source_filename=reading.source_filename,
                                     source_sha256=reading.source_sha256,
                                     source_row_number=reading.source_row_number),
    )


def _clamp(limit: int) -> int:
    return min(limit, settings.structured_query_max_limit)


def maintenance_history(session, equipment_tag=None, work_order_id=None, maintenance_type=None,
                         status=None, start=None, end=None, limit=50):
    stmt = select(MaintenanceRecord, Equipment.equipment_tag).join(
        Equipment, MaintenanceRecord.equipment_id == Equipment.id)
    if equipment_tag:
        stmt = stmt.where(Equipment.equipment_tag == normalize_equipment_tag(equipment_tag))
    if work_order_id:
        stmt = stmt.where(MaintenanceRecord.work_order_id == work_order_id)
    if maintenance_type:
        stmt = stmt.where(MaintenanceRecord.maintenance_type == maintenance_type.lower())
    if status:
        stmt = stmt.where(MaintenanceRecord.status == status)
    if start:
        stmt = stmt.where(MaintenanceRecord.maintenance_date >= start)
    if end:
        stmt = stmt.where(MaintenanceRecord.maintenance_date <= end)
    stmt = stmt.order_by(
        case((MaintenanceRecord.maintenance_date.is_(None), 1), else_=0),
        MaintenanceRecord.maintenance_date.desc(),
        MaintenanceRecord.created_at.desc(), MaintenanceRecord.id.desc(),
    ).limit(_clamp(limit))
    return [maintenance_out(record, tag) for record, tag in session.execute(stmt).all()]


def work_order_lookup(session, work_order_id):
    return maintenance_history(session, work_order_id=work_order_id, limit=settings.structured_query_max_limit)


def sensor_readings_query(session, equipment_tag=None, sensor_tag=None, measurement=None,
                           start=None, end=None, limit=200):
    stmt = select(SensorReading, Equipment.equipment_tag).join(
        Equipment, SensorReading.equipment_id == Equipment.id)
    if equipment_tag:
        stmt = stmt.where(Equipment.equipment_tag == normalize_equipment_tag(equipment_tag))
    if sensor_tag:
        stmt = stmt.where(SensorReading.sensor_tag == sensor_tag)
    if measurement:
        stmt = stmt.where(SensorReading.sensor_type == measurement.lower())
    if start:
        stmt = stmt.where(SensorReading.timestamp >= start)
    if end:
        stmt = stmt.where(SensorReading.timestamp <= end)
    stmt = stmt.order_by(SensorReading.timestamp.asc(), SensorReading.id).limit(_clamp(limit))
    return [sensor_out(reading, tag) for reading, tag in session.execute(stmt).all()]


def sensor_latest(session, equipment_tag, sensor_tag=None):
    stmt = select(SensorReading, Equipment.equipment_tag).join(
        Equipment, SensorReading.equipment_id == Equipment.id
    ).where(Equipment.equipment_tag == normalize_equipment_tag(equipment_tag))
    if sensor_tag:
        stmt = stmt.where(SensorReading.sensor_tag == sensor_tag)
    ranked = stmt.with_only_columns(SensorReading.id, func.row_number().over(
        partition_by=SensorReading.sensor_tag,
        order_by=(SensorReading.timestamp.desc(), SensorReading.id.desc())).label("rank")).subquery()
    query = select(SensorReading, Equipment.equipment_tag).join(Equipment).join(ranked, ranked.c.id == SensorReading.id)
    rows = session.execute(query.where(ranked.c.rank == 1).order_by(SensorReading.sensor_tag, SensorReading.id)
                           .limit(settings.structured_query_max_limit)).all()
    return [sensor_out(reading, tag) for reading, tag in rows]


def sensor_features_query(session, request, as_of, write_artifact=True) -> SensorFeatureResponse:
    rows = session.execute(
        select(SensorReading, Equipment.equipment_tag).join(
            Equipment, SensorReading.equipment_id == Equipment.id
        ).where(
            Equipment.equipment_tag == normalize_equipment_tag(request.equipment_tag),
            SensorReading.sensor_tag == request.sensor_tag,
            SensorReading.timestamp >= request.start,
            SensorReading.timestamp <= request.end,
        ).order_by(SensorReading.timestamp.asc())
    ).all()
    warnings = []
    if not rows:
        warnings.append("No sensor readings were found for this equipment/sensor/window.")
    values = [reading.value for reading, _ in rows]
    dict_readings = [{"value": r.value, "timestamp": r.timestamp, "quality": r.quality} for r, _ in rows]
    measurement = rows[0][0].sensor_type if rows else None
    units = {reading.unit for reading, _ in rows if reading.unit}
    unit = next(iter(units)) if len(units) == 1 else None
    if len(units) > 1:
        warnings.append("Multiple units were present in this window; unit is not reported as a single value.")
    features = compute_features(values, request.rolling_window)
    observations = detect_anomalies(dict_readings, request.thresholds, measurement or request.sensor_tag, unit, as_of=as_of)
    provenance = [StructuredCitation(source_filename=r.source_filename, source_sha256=r.source_sha256,
                                      source_row_number=r.source_row_number) for r, _ in rows]
    citation_label = (
        f"{request.equipment_tag}/{request.sensor_tag} {rows[0][0].source_filename} {request.start.isoformat()} to {request.end.isoformat()}" if rows
        else f"{request.equipment_tag}/{request.sensor_tag} {request.start.isoformat()} to {request.end.isoformat()}"
    )
    response = SensorFeatureResponse(
        equipment_tag=normalize_equipment_tag(request.equipment_tag), sensor_tag=request.sensor_tag,
        measurement=measurement, unit=unit, window_start=request.start, window_end=request.end,
        features=features, observations=observations, warnings=warnings,
        citation_label=citation_label, provenance=provenance,
    )
    if write_artifact:
        write_json(settings.data_root / "processed/sensors/features" / f"{uuid4()}.json",
                   response.model_dump(mode="json"))
    return response
