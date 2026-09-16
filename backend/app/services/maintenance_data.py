"""Maintenance CSV parsing and ingestion. No diagnostic inference; rows only."""
import csv
import io
import math
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, text

from app.core.config import settings
from app.db.models.structured_data_source import StructuredDataSource
from app.db.models.maintenance_record import MaintenanceRecord
from app.schemas.structured import StructuredIngestResponse
from app.services.extraction import source_sha256
from app.services.ingestion import IngestionConflict, write_json
from app.services.structured_paths import resolve_structured_source, read_csv_source, decode_csv, advisory_lock_key
from app.services.equipment_tags import find_or_create_equipment

REQUIRED_HEADERS = {"equipment_tag"}
KNOWN_MAINTENANCE_TYPES = {"preventive", "corrective", "inspection", "overhaul"}


def parse_timestamp(value: str) -> datetime | None:
    text_value = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_float(value: str) -> float | None:
    try:
        result = float(value)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def clean(value) -> str | None:
    value = (value or "").strip()
    return value or None


def parse_maintenance_csv(text_content: str):
    """Returns (rows, warnings, rejected_row_count). Malformed dates/numbers keep
    the row with a null field and a warning; missing equipment_tag rejects the row."""
    reader = csv.DictReader(io.StringIO(text_content))
    headers = set(reader.fieldnames or [])
    missing = REQUIRED_HEADERS - headers
    if missing:
        raise ValueError(f"Missing required CSV headers: {sorted(missing)}")
    rows, warnings, rejected, seen = [], [], 0, set()
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
        if not raw_tag:
            warnings.append(f"row {line_number}: missing equipment_tag; row skipped")
            rejected += 1
            continue
        maintenance_type_raw = clean(raw.get("maintenance_type"))
        maintenance_type = maintenance_type_raw.lower() if maintenance_type_raw else None
        if maintenance_type and maintenance_type not in KNOWN_MAINTENANCE_TYPES:
            warnings.append(f"row {line_number}: unrecognized maintenance_type '{maintenance_type}'")
        date_raw = clean(raw.get("maintenance_date"))
        maintenance_date = parse_timestamp(date_raw) if date_raw else None
        if date_raw and maintenance_date is None:
            warnings.append(f"row {line_number}: invalid maintenance_date '{date_raw}'; stored as null")
        downtime_raw = clean(raw.get("downtime_hours"))
        downtime_hours = parse_float(downtime_raw) if downtime_raw else None
        if downtime_raw and downtime_hours is None:
            warnings.append(f"row {line_number}: invalid downtime_hours '{downtime_raw}'; stored as null")
        rows.append({
            "raw_equipment_tag": raw_tag, "work_order_id": clean(raw.get("work_order_id")),
            "maintenance_type": maintenance_type, "failure_mode": clean(raw.get("failure_mode")),
            "maintenance_date": maintenance_date, "description": clean(raw.get("description")),
            "downtime_hours": downtime_hours, "parts_replaced": clean(raw.get("parts_replaced")),
            "technician_notes": clean(raw.get("technician_notes")), "status": clean(raw.get("status")),
            "source_row_number": line_number, "raw": raw,
        })
    return rows, warnings, rejected


def request_metadata(request):
    return request.model_dump(mode="json", exclude={"source_path"})


def ingest_response(source, status):
    return StructuredIngestResponse(
        source_id=source.id, source_type="maintenance", filename=source.source_filename,
        source_sha256=source.source_sha256, status=status, row_count=source.row_count,
        rejected_row_count=source.rejected_row_count, warnings=source.warnings,
    )


def json_row(row, equipment_tag):
    return {
        "equipment_tag": equipment_tag, "raw_equipment_tag": row["raw_equipment_tag"],
        "work_order_id": row["work_order_id"], "maintenance_type": row["maintenance_type"],
        "failure_mode": row["failure_mode"],
        "maintenance_date": row["maintenance_date"].isoformat() if row["maintenance_date"] else None,
        "description": row["description"], "downtime_hours": row["downtime_hours"],
        "parts_replaced": row["parts_replaced"], "technician_notes": row["technician_notes"],
        "status": row["status"], "source_row_number": row["source_row_number"],
    }


def ingest_maintenance(request, session):
    path = resolve_structured_source(request.source_path, "maintenance")
    source_bytes = read_csv_source(path)
    checksum = source_sha256(source_bytes)
    if not session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": advisory_lock_key(checksum)}):
        raise IngestionConflict("This source is already being ingested; retry later")
    existing = session.scalar(select(StructuredDataSource).where(StructuredDataSource.source_sha256 == checksum))
    metadata = request_metadata(request)
    if existing:
        if existing.source_type != "maintenance" or existing.ingestion_metadata != metadata:
            raise IngestionConflict("This checksum is already registered with a different source type or metadata")
        return ingest_response(existing, "duplicate")
    rows, warnings, rejected = parse_maintenance_csv(decode_csv(source_bytes))
    if not rows:
        warnings = warnings + ["No usable maintenance rows were parsed from this CSV."]
    source_record = StructuredDataSource(
        id=uuid4(), source_type="maintenance", source_filename=path.name,
        source_uri=path.relative_to(settings.data_root).as_posix(), source_sha256=checksum,
        status="ingested", row_count=len(rows), rejected_row_count=rejected,
        ingestion_metadata=metadata, warnings=warnings,
    )
    session.add(source_record)
    session.flush()
    normalized = []
    for row in rows:
        equipment = find_or_create_equipment(session, row["raw_equipment_tag"])
        session.add(MaintenanceRecord(
            id=uuid4(), equipment_id=equipment.id, raw_equipment_tag=row["raw_equipment_tag"],
            work_order_id=row["work_order_id"], maintenance_type=row["maintenance_type"],
            failure_mode=row["failure_mode"], maintenance_date=row["maintenance_date"],
            description=row["description"], downtime_hours=row["downtime_hours"],
            parts_replaced=row["parts_replaced"], technician_notes=row["technician_notes"],
            status=row["status"], source_filename=path.name, source_sha256=checksum,
            source_row_number=row["source_row_number"], raw_row=row["raw"],
        ))
        normalized.append(json_row(row, equipment.equipment_tag))
    write_json(settings.data_root / "processed/maintenance/normalized" / f"{source_record.id}.json", {
        "source_id": str(source_record.id), "source_filename": path.name,
        "source_sha256": checksum, "rows": normalized,
    })
    session.commit()
    return ingest_response(source_record, "ingested")
