"""Sensor time-series CSV parsing and ingestion. No diagnostic inference; readings only."""
import csv
import io
from uuid import uuid4

from sqlalchemy import select, text

from app.core.config import settings
from app.db.models.structured_data_source import StructuredDataSource
from app.db.models.sensor_reading import SensorReading
from app.schemas.structured import StructuredIngestResponse
from app.services.extraction import source_sha256
from app.services.ingestion import IngestionConflict, write_json
from app.services.structured_paths import resolve_structured_source, read_csv_source, decode_csv, advisory_lock_key
from app.services.equipment_tags import find_or_create_equipment
from app.services.maintenance_data import parse_timestamp, parse_float, clean

REQUIRED_HEADERS = {"timestamp", "equipment_tag", "sensor_tag", "measurement", "value"}


def parse_sensor_csv(text_content: str):
    """Returns (rows, warnings, rejected_row_count). A row missing an identity field,
    timestamp, or numeric value is rejected; no measurement is ever guessed."""
    reader = csv.DictReader(io.StringIO(text_content))
    headers = set(reader.fieldnames or [])
    missing = REQUIRED_HEADERS - headers
    if missing:
        raise ValueError(f"Missing required CSV headers: {sorted(missing)}")
    rows, warnings, rejected, seen, last_value = [], [], 0, set(), {}
    for line_number, raw in enumerate(reader, start=2):
        if line_number - 1 > settings.structured_csv_max_rows:
            raise ValueError(f"CSV exceeds {settings.structured_csv_max_rows} data rows")
        raw = {key: (value or "") for key, value in raw.items() if key is not None}
        fingerprint = tuple(sorted(raw.items()))
        if fingerprint in seen:
            warnings.append(f"row {line_number}: duplicate record skipped")
            rejected += 1
            continue
        seen.add(fingerprint)
        raw_tag = clean(raw.get("equipment_tag"))
        sensor_tag = clean(raw.get("sensor_tag"))
        measurement = clean(raw.get("measurement"))
        timestamp_raw = clean(raw.get("timestamp"))
        value_raw = clean(raw.get("value"))
        problems = []
        if not raw_tag:
            problems.append("missing equipment_tag")
        if not sensor_tag:
            problems.append("missing sensor_tag")
        if not measurement:
            problems.append("missing measurement")
        timestamp = parse_timestamp(timestamp_raw) if timestamp_raw else None
        if not timestamp_raw:
            problems.append("missing timestamp")
        elif timestamp is None:
            problems.append(f"invalid timestamp '{timestamp_raw}'")
        value = parse_float(value_raw) if value_raw else None
        if not value_raw:
            problems.append("missing value")
        elif value is None:
            problems.append(f"invalid value '{value_raw}'")
        if problems:
            warnings.append(f"row {line_number}: {'; '.join(problems)}; row skipped")
            rejected += 1
            continue
        quality = clean(raw.get("quality"))
        quality = quality.lower() if quality else None
        key = (raw_tag, sensor_tag, timestamp.isoformat())
        if key in last_value and last_value[key] != value:
            warnings.append(
                f"row {line_number}: conflicting reading at the same timestamp for {raw_tag}/{sensor_tag}; both retained"
            )
        last_value[key] = value
        rows.append({
            "raw_equipment_tag": raw_tag, "sensor_tag": sensor_tag, "measurement": measurement.lower(),
            "value": value, "unit": clean(raw.get("unit")), "quality": quality, "timestamp": timestamp,
            "source_row_number": line_number, "raw": raw,
        })
    return rows, warnings, rejected


def request_metadata(request):
    return request.model_dump(mode="json", exclude={"source_path"})


def ingest_response(source, status):
    return StructuredIngestResponse(
        source_id=source.id, source_type="sensor", filename=source.source_filename,
        source_sha256=source.source_sha256, status=status, row_count=source.row_count,
        rejected_row_count=source.rejected_row_count, warnings=source.warnings,
    )


def json_row(row, equipment_tag):
    return {
        "equipment_tag": equipment_tag, "raw_equipment_tag": row["raw_equipment_tag"],
        "sensor_tag": row["sensor_tag"], "measurement": row["measurement"], "value": row["value"],
        "unit": row["unit"], "quality": row["quality"], "timestamp": row["timestamp"].isoformat(),
        "source_row_number": row["source_row_number"],
    }


def ingest_sensor(request, session):
    path = resolve_structured_source(request.source_path, "sensors")
    source_bytes = read_csv_source(path)
    checksum = source_sha256(source_bytes)
    if not session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": advisory_lock_key(checksum)}):
        raise IngestionConflict("This source is already being ingested; retry later")
    existing = session.scalar(select(StructuredDataSource).where(StructuredDataSource.source_sha256 == checksum))
    metadata = request_metadata(request)
    if existing:
        if existing.source_type != "sensor" or existing.ingestion_metadata != metadata:
            raise IngestionConflict("This checksum is already registered with a different source type or metadata")
        return ingest_response(existing, "duplicate")
    rows, warnings, rejected = parse_sensor_csv(decode_csv(source_bytes))
    if not rows:
        warnings = warnings + ["No usable sensor readings were parsed from this CSV."]
    source_record = StructuredDataSource(
        id=uuid4(), source_type="sensor", source_filename=path.name,
        source_uri=path.relative_to(settings.data_root).as_posix(), source_sha256=checksum,
        status="ingested", row_count=len(rows), rejected_row_count=rejected,
        ingestion_metadata=metadata, warnings=warnings,
    )
    session.add(source_record)
    session.flush()
    normalized = []
    for row in rows:
        equipment = find_or_create_equipment(session, row["raw_equipment_tag"])
        session.add(SensorReading(
            id=uuid4(), equipment_id=equipment.id, sensor_tag=row["sensor_tag"],
            sensor_type=row["measurement"], value=row["value"], unit=row["unit"], quality=row["quality"],
            timestamp=row["timestamp"], source_filename=path.name, source_sha256=checksum,
            source_row_number=row["source_row_number"],
        ))
        normalized.append(json_row(row, equipment.equipment_tag))
    write_json(settings.data_root / "processed/sensors/normalized" / f"{source_record.id}.json", {
        "source_id": str(source_record.id), "source_filename": path.name,
        "source_sha256": checksum, "rows": normalized,
    })
    session.commit()
    return ingest_response(source_record, "ingested")
