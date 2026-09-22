"""Phase 5D cryptographic evidence integrity: freeze an immutable evidence
manifest at governance time, and deterministically re-verify it later.

Evidence INTEGRITY is not evidence CORRECTNESS, OCR confidence, authorization,
or plant-state truth. This module only ever answers: "is this the exact
evidence content that was present when the revision was created, and does it
still match its authoritative source where re-verification is possible?" It
never judges whether the evidence is factually right, whether OCR read a
label correctly, whether anyone was authorized to act on it, or the real
state of any valve/process. See docs/phase5d.md.

No governance/authorization decision is made here -- app.services.governance
and app.services.approval remain the sole authority for approve/reject/
release. This module only reports integrity facts for them to act on.
"""
from datetime import timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import DocumentVersion, EvidenceManifest, EvidenceManifestItem, MaintenanceRecord, SensorReading
from app.services.canonicalization import canonical_hash, canonical_json

MANIFEST_VERSION = "phase5d-evidence-v1"
# Deterministic normalization applied to a maintenance/sensor record's field
# values before hashing -- versioned so a future normalization change is
# itself detectable, never a silent redefinition of what "the same record"
# hashes to.
RECORD_NORMALIZATION_VERSION = "phase5d-record-v1"


class EvidenceIntegrityError(RuntimeError):
    """Mandatory manifest persistence failed. The caller must fail closed --
    same reasoning as app.services.audit.AuditChainError."""


def _insert_once(session, model, values):
    dialect = session.get_bind().dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise ValueError("Unsupported evidence database")
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    session.execute(insert(model).values(**values).on_conflict_do_nothing())


# -- Content resolution, one per app.agents.evidence.EvidenceRef `kind` -----

def _document_chunk_content(ref: dict) -> tuple[str, dict, str]:
    content_hash = canonical_hash(ref.get("quote", ""))
    provenance = {
        "document_id": ref.get("document_id"), "document_version_id": ref.get("document_version_id"),
        "chunk_id": ref.get("chunk_id"), "page_start": ref.get("page_start"), "page_end": ref.get("page_end"),
        "section_path": ref.get("section_path"), "bounding_boxes": ref.get("bounding_boxes"),
        "ocr_derived": ref.get("ocr_derived"), "ocr_confidence": ref.get("ocr_confidence"),
        "ocr_status": ref.get("ocr_status"),
    }
    source_identifier = f"document:{ref.get('document_id')}:chunk:{ref.get('chunk_id')}"
    return content_hash, provenance, source_identifier


def _pid_region_content(ref: dict) -> tuple[str, dict, str]:
    content_hash = canonical_hash(ref.get("combined_text", ""))
    provenance = {
        "document_id": ref.get("document_id"), "document_version_id": ref.get("document_version_id"),
        "region_id": ref.get("region_id"), "page": ref.get("page"), "bbox": list(ref.get("bbox") or []),
        "confidence": ref.get("confidence"), "ocr_status": ref.get("ocr_status"),
    }
    if ref.get('ocr_region_hash'):
        provenance.update(ocr_region_hash=ref['ocr_region_hash'], revision=ref.get('revision'),
                          text_items=ref.get('text_items', []), source_image_uri=ref.get('source_image_uri'))
    source_identifier = f"document:{ref.get('document_id')}:region:{ref.get('region_id')}"
    return content_hash, provenance, source_identifier


def _lookup_csv_row(session, source_sha256: str, source_row_number: int):
    """A "csv_row" EvidenceRef doesn't say which table it came from -- try
    both existing structured-data tables by their existing
    UniqueConstraint(source_sha256, source_row_number) key. Returns
    ("maintenance_records" | "sensor_readings" | None, row | None)."""
    record = session.execute(
        select(MaintenanceRecord).where(MaintenanceRecord.source_sha256 == source_sha256,
                                        MaintenanceRecord.source_row_number == source_row_number)
    ).scalar_one_or_none()
    if record is not None:
        return "maintenance_records", record
    reading = session.execute(
        select(SensorReading).where(SensorReading.source_sha256 == source_sha256,
                                    SensorReading.source_row_number == source_row_number)
    ).scalar_one_or_none()
    if reading is not None:
        return "sensor_readings", reading
    return None, None


def _maintenance_record_fields(record) -> dict:
    return {
        "equipment_id": str(record.equipment_id), "raw_equipment_tag": record.raw_equipment_tag,
        "work_order_id": record.work_order_id, "maintenance_type": record.maintenance_type,
        "failure_mode": record.failure_mode, "maintenance_date": _aware_utc(record.maintenance_date),
        "description": record.description, "downtime_hours": record.downtime_hours,
        "parts_replaced": record.parts_replaced, "technician_notes": record.technician_notes,
        "status": record.status, "normalization_version": RECORD_NORMALIZATION_VERSION,
    }


def _aware_utc(value):
    # SQLite (test fixtures only) returns naive datetimes even for
    # DateTime(timezone=True); PostgreSQL never does. Treat a naive value as
    # already UTC, matching app.services.governance/app.services.audit's
    # identical documented SQLite workaround.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _sensor_reading_fields(reading) -> dict:
    return {
        "equipment_id": str(reading.equipment_id), "sensor_tag": reading.sensor_tag,
        "sensor_type": reading.sensor_type, "value": reading.value, "unit": reading.unit,
        "quality": reading.quality, "timestamp": _aware_utc(reading.timestamp),
        "normalization_version": RECORD_NORMALIZATION_VERSION,
    }


def _csv_row_content(session, ref: dict) -> tuple[str, dict, str]:
    table, row = _lookup_csv_row(session, ref.get("source_sha256", ""), ref.get("source_row_number", -1))
    if table == "maintenance_records":
        content_hash = canonical_hash(_maintenance_record_fields(row))
        provenance = {"table": table, "record_id": str(row.id), "equipment_id": str(row.equipment_id),
                     "work_order_id": row.work_order_id}
        source_identifier = f"maintenance_record:{row.id}"
    elif table == "sensor_readings":
        content_hash = canonical_hash(_sensor_reading_fields(row))
        provenance = {"table": table, "record_id": str(row.id), "equipment_id": str(row.equipment_id),
                     "sensor_tag": row.sensor_tag}
        source_identifier = f"sensor_reading:{row.id}"
    else:
        # Row not found at freeze time (already deleted, or the source hash
        # doesn't correspond to either table) -- bind that fact honestly
        # rather than fabricate content; re-verification will keep failing to
        # resolve it too, which is itself the correct detection outcome.
        content_hash = canonical_hash({"unresolved": True, "source_sha256": ref.get("source_sha256"),
                                       "source_row_number": ref.get("source_row_number")})
        provenance = {"table": None, "note": "source row not found in maintenance_records or sensor_readings"}
        source_identifier = f"unresolved:{ref.get('source_sha256')}:{ref.get('source_row_number')}"
    return content_hash, provenance, source_identifier


def _resolve_window_reading_hashes(session, citations: list[dict]) -> tuple[list[str], list, int]:
    """Shared by freeze and re-verify: resolve an ORDERED list of
    {source_sha256, source_row_number} citations to per-reading hashes, in
    the SAME order (order is part of what gets hashed). Returns
    (ordered_hashes, resolved_timestamps, unresolved_count)."""
    reading_hashes = []
    timestamps = []
    unresolved = 0
    for citation in citations:
        source_sha256 = citation.get("source_sha256")
        source_row_number = citation.get("source_row_number")
        reading = session.execute(
            select(SensorReading).where(SensorReading.source_sha256 == source_sha256,
                                        SensorReading.source_row_number == source_row_number)
        ).scalar_one_or_none()
        if reading is None:
            reading_hashes.append(canonical_hash({"unresolved": True, "source_sha256": source_sha256,
                                                  "source_row_number": source_row_number}))
            unresolved += 1
            continue
        reading_hashes.append(canonical_hash(_sensor_reading_fields(reading)))
        timestamps.append(_aware_utc(reading.timestamp))
    return reading_hashes, timestamps, unresolved


def _sensor_window_content(session, ref: dict) -> tuple[str, dict, str]:
    citations = ref.get("provenance") or []
    reading_hashes, timestamps, unresolved = _resolve_window_reading_hashes(session, citations)
    window_start = min(timestamps) if timestamps else None
    window_end = max(timestamps) if timestamps else None
    content_hash = canonical_hash({
        "ordered_reading_hashes": reading_hashes, "reading_count": len(reading_hashes),
        "window_start": window_start, "window_end": window_end,
        "normalization_version": RECORD_NORMALIZATION_VERSION,
    })
    provenance = {
        # The ORIGINAL ordered citation list is kept (small: a few dozen
        # {source_sha256, source_row_number} pairs at most, never raw sensor
        # values) so re-verification can replay the exact same resolution
        # later, not merely compare derived summary statistics.
        "citation_label": ref.get("citation_label"), "citations": citations,
        "reading_count": len(reading_hashes), "unresolved_count": unresolved,
        "window_start": window_start.isoformat() if window_start else None,
        "window_end": window_end.isoformat() if window_end else None,
    }
    source_identifier = f"sensor_window:{ref.get('citation_label')}"
    return content_hash, provenance, source_identifier


def _item_content(session, evidence_type: str, ref: dict) -> tuple[str, dict, str]:
    if evidence_type == "document_chunk":
        return _document_chunk_content(ref)
    if evidence_type == "pid_region":
        return _pid_region_content(ref)
    if evidence_type == "csv_row":
        return _csv_row_content(session, ref)
    if evidence_type == "sensor_window":
        return _sensor_window_content(session, ref)
    raise ValueError(f"Unsupported evidence_type {evidence_type!r}")


def _item_envelope(*, evidence_type, evidence_id, source_identifier, source_hash, content_hash, provenance) -> dict:
    return {
        "manifest_version": MANIFEST_VERSION, "evidence_type": evidence_type, "evidence_id": evidence_id,
        "source_identifier": source_identifier, "source_hash": source_hash, "content_hash": content_hash,
        "provenance": provenance,
    }


def _manifest_envelope(*, action_revision_id, items: list[dict]) -> dict:
    return {
        "manifest_version": MANIFEST_VERSION, "action_revision_id": str(action_revision_id),
        "item_count": len(items),
        "items": [{"item_index": index, "evidence_type": item["evidence_type"], "evidence_id": item["evidence_id"],
                  "canonical_item_hash": item["canonical_item_hash"]} for index, item in enumerate(items)],
    }


def freeze_manifest(session, *, action_revision_id: UUID, evidence: list[dict]) -> EvidenceManifest:
    """Build and insert the immutable manifest for a just-created
    ActionRevision, in the CALLER's transaction (never commits here -- see
    app.services.audit.append_event for the identical same-transaction
    convention this mirrors). `evidence` is the already-canonicalized list of
    EvidenceRef dicts from app.services.governance._proposal_payload -- the
    exact frozen snapshot, never re-fetched from the live graph state.
    """
    try:
        items = []
        for evidence_ref in evidence:
            evidence_type = evidence_ref.get("kind")
            content_hash, provenance, source_identifier = _item_content(session, evidence_type, evidence_ref)
            source_hash = evidence_ref.get("source_sha256", "")
            canonical_item_hash = canonical_hash(_item_envelope(
                evidence_type=evidence_type, evidence_id=evidence_ref.get("evidence_id"),
                source_identifier=source_identifier, source_hash=source_hash, content_hash=content_hash,
                provenance=provenance,
            ))
            items.append({
                "evidence_type": evidence_type, "evidence_id": evidence_ref.get("evidence_id"),
                "source_identifier": source_identifier, "source_hash": source_hash, "content_hash": content_hash,
                "provenance": provenance, "canonical_item_hash": canonical_item_hash,
            })

        envelope = _manifest_envelope(action_revision_id=action_revision_id, items=items)
        canonical_manifest = canonical_json(envelope)
        canonical_manifest_hash = canonical_hash(envelope)

        _insert_once(session, EvidenceManifest, {
            "action_revision_id": action_revision_id, "manifest_version": MANIFEST_VERSION,
            "canonical_manifest": canonical_manifest, "canonical_manifest_hash": canonical_manifest_hash,
            "item_count": len(items), "integrity_status": "PENDING_INTEGRITY",
        })
        manifest = session.execute(
            select(EvidenceManifest).where(EvidenceManifest.action_revision_id == action_revision_id)
        ).scalar_one()

        for index, item in enumerate(items):
            _insert_once(session, EvidenceManifestItem, {
                "manifest_id": manifest.id, "item_index": index, **item,
            })
        session.flush()
        return manifest
    except Exception as error:
        raise EvidenceIntegrityError(f"Evidence manifest freeze failed: {error}") from error


def verify_manifest(session, revision_id: UUID) -> dict:
    """Deterministic re-verification -- never an LLM. Returns:

    {"valid": bool, "manifest_id": UUID | None, "action_revision_id": UUID,
     "item_count": int, "items_checked": int, "first_error_item_index": int | None,
     "error_type": str | None}

    error_type vocabulary: "manifest_missing", "manifest_hash_mismatch",
    "item_hash_mismatch", "source_content_changed", "source_missing"
    (csv_row/maintenance/sensor-reading kind); "document_provenance_missing",
    "document_version_unresolved", "document_source_hash_mismatch"
    (document_chunk/pid_region kind); "sensor_window_incomplete",
    "sensor_reading_unresolved", "sensor_evidence_mismatch" (sensor_window kind).
    """
    result = {"valid": True, "manifest_id": None, "action_revision_id": revision_id, "item_count": 0,
             "items_checked": 0, "first_error_item_index": None, "error_type": None}

    manifest = session.execute(
        select(EvidenceManifest).where(EvidenceManifest.action_revision_id == revision_id)
    ).scalar_one_or_none()
    if manifest is None:
        result["valid"] = False
        result["error_type"] = "manifest_missing"
        return result

    result["manifest_id"] = manifest.id
    result["item_count"] = manifest.item_count

    items = session.execute(
        select(EvidenceManifestItem).where(EvidenceManifestItem.manifest_id == manifest.id)
        .order_by(EvidenceManifestItem.item_index)
    ).scalars().all()

    envelope = _manifest_envelope(
        action_revision_id=revision_id,
        items=[{"evidence_type": item.evidence_type, "evidence_id": item.evidence_id,
               "canonical_item_hash": item.canonical_item_hash} for item in items],
    )
    recomputed_manifest_text = canonical_json(envelope)
    recomputed_manifest_hash = canonical_hash(envelope)
    if (recomputed_manifest_text != manifest.canonical_manifest
            or recomputed_manifest_hash != manifest.canonical_manifest_hash
            or len(items) != manifest.item_count):
        result["valid"] = False
        result["error_type"] = "manifest_hash_mismatch"
        return result

    for item in items:
        result["items_checked"] += 1
        recomputed_item_hash = canonical_hash(_item_envelope(
            evidence_type=item.evidence_type, evidence_id=item.evidence_id,
            source_identifier=item.source_identifier, source_hash=item.source_hash,
            content_hash=item.content_hash, provenance=item.provenance,
        ))
        if recomputed_item_hash != item.canonical_item_hash:
            result["valid"] = False
            result["first_error_item_index"] = item.item_index
            result["error_type"] = "item_hash_mismatch"
            return result

        # Live re-verification against the authoritative source, where
        # possible -- this is what catches a source row/document mutated
        # AFTER the manifest was frozen, which the manifest's own internal
        # self-consistency (checked above) cannot detect by itself.
        ok, error_type = _reverify_against_source(session, item)
        if not ok:
            result["valid"] = False
            result["first_error_item_index"] = item.item_index
            result["error_type"] = error_type
            return result

    return result


def _reverify_against_source(session, item: EvidenceManifestItem) -> tuple[bool, str | None]:
    provenance = item.provenance or {}

    if item.evidence_type in ("document_chunk", "pid_region"):
        # Astra finding 1 (HIGH): document_version_id is a REQUIRED field on
        # every DocumentChunkEvidence/PIDRegionEvidence (see
        # app.agents.evidence) -- a legitimately-frozen item NEVER lacks it.
        # There is no genuine "legacy" case here (Phase 5D always populated
        # this field from day one); missing/empty/malformed provenance is
        # only reachable via a forged or corrupted row, so it must fail
        # closed, never silently pass re-verification.
        document_version_id = provenance.get("document_version_id")
        if not document_version_id:
            return False, "document_provenance_missing"
        try:
            version_uuid = UUID(str(document_version_id))
        except (ValueError, TypeError, AttributeError):
            return False, "document_provenance_missing"
        version = session.get(DocumentVersion, version_uuid)
        if version is None:
            return False, "document_version_unresolved"
        if not item.source_hash or version.source_sha256 != item.source_hash:
            return False, "document_source_hash_mismatch"
        if item.evidence_type == 'pid_region' and provenance.get('ocr_region_hash'):
            from app.services.pid_evidence import load_pid_evidence
            try:
                refs = load_pid_evidence(session, version_uuid)
                fresh = next((r for r in refs if r.region_id == provenance.get('region_id')), None)
                if fresh is None:
                    return False, 'source_missing'
                content_hash, fresh_provenance, _ = _pid_region_content(fresh.model_dump(mode='json'))
                if content_hash != item.content_hash or canonical_hash(fresh_provenance) != canonical_hash(provenance):
                    return False, 'source_content_changed'
            except (ValueError, OSError, KeyError, TypeError):
                return False, 'source_content_changed'
        return True, None

    if item.evidence_type == "csv_row":
        table, record_id = provenance.get("table"), provenance.get("record_id")
        if table is None:
            return False, "source_missing"  # was already unresolved at freeze time
        model = MaintenanceRecord if table == "maintenance_records" else SensorReading
        row = session.get(model, UUID(record_id))
        if row is None:
            return False, "source_missing"
        fresh_fields = _maintenance_record_fields(row) if table == "maintenance_records" else _sensor_reading_fields(row)
        if canonical_hash(fresh_fields) != item.content_hash:
            return False, "source_content_changed"
        return True, None

    if item.evidence_type == "sensor_window":
        # Astra finding 2 (HIGH): a sensor_window item is ALWAYS frozen with a
        # "citations" list in provenance (see _sensor_window_content, which
        # sets it unconditionally, even to []) -- there is no genuine legacy
        # case where it is absent, so a missing list must fail closed rather
        # than silently pass, the same reasoning as finding 1 above.
        citations = provenance.get("citations")
        if citations is None:
            return False, "sensor_window_incomplete"

        reading_hashes, timestamps, unresolved = _resolve_window_reading_hashes(session, citations)
        # The bug: `unresolved` was computed but never checked. A reading
        # that doesn't resolve still gets a deterministic "unresolved"
        # placeholder hash from _resolve_window_reading_hashes, appended in
        # its citation's ordered position -- so if a citation was ALREADY
        # unresolvable when the manifest was frozen, freeze-time and
        # verify-time both compute the exact same placeholder hash and the
        # content-hash comparison below matches trivially, even though real
        # evidence was never bound. Every cited reading must actually
        # resolve; the expected count (every citation) must equal the
        # resolved count (citations minus unresolved) -- i.e. unresolved
        # must be exactly zero -- checked BEFORE trusting any hash match.
        if unresolved > 0:
            return False, "sensor_reading_unresolved"

        window_start = min(timestamps) if timestamps else None
        window_end = max(timestamps) if timestamps else None
        fresh_content_hash = canonical_hash({
            "ordered_reading_hashes": reading_hashes, "reading_count": len(reading_hashes),
            "window_start": window_start, "window_end": window_end,
            "normalization_version": RECORD_NORMALIZATION_VERSION,
        })
        if fresh_content_hash != item.content_hash:
            return False, "sensor_evidence_mismatch"
        return True, None

    return True, None


def get_evidence_integrity_status(session, revision_id: UUID) -> str:
    """The LIVE, always-recomputed status -- never a cached/stored flag (see
    app.db.models.EvidenceManifest.integrity_status, which stays the frozen
    constant "PENDING_INTEGRITY" forever by DB CHECK constraint). Returns one
    of "VERIFIED", "FAILED", "LEGACY_UNVERIFIED" -- a revision with no
    manifest at all (created before Phase 5D existed) is honestly labeled
    LEGACY_UNVERIFIED, never VERIFIED merely because it exists."""
    manifest = session.execute(
        select(EvidenceManifest).where(EvidenceManifest.action_revision_id == revision_id)
    ).scalar_one_or_none()
    if manifest is None:
        return "LEGACY_UNVERIFIED"
    return "VERIFIED" if verify_manifest(session, revision_id)["valid"] else "FAILED"
