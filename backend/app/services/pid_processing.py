"""P&ID OCR artifacts backed by existing document/version records."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select, text
from app.core.config import settings
from app.db.models.document import Document
from app.db.models.document_version import DocumentVersion
from app.schemas.pid import PIDManifest, PIDProcessResponse
from app.services.extraction import source_sha256
from app.services.ingestion import IngestionConflict, write_json
from app.services.pid_images import read_pid_source, render_pages
from app.services.pid_regions import group_regions, merged_tags
from app.services.paddle_ocr import get_paddle_ocr, OCR_MODELS


def request_metadata(request):
    return request.model_dump(mode="json", exclude={"source_path", "document_id"})


def check_duplicate(version, request):
    metadata = version.ingestion_metadata
    if metadata.get("kind") != "pid" or metadata.get("request") != request_metadata(request):
        raise IngestionConflict("Source already exists with different pipeline or metadata; existing artifacts were preserved")
    if request.document_id and version.document_id != request.document_id:
        raise IngestionConflict("Source already belongs to another document")
    return version.status in ("pid_processed", "pid_indexed", "pid_index_failed")


def manifest_response(manifest, uri, status):
    return PIDProcessResponse(
        document_id=manifest.document_id, document_version_id=manifest.document_version_id,
        filename=manifest.source_filename, source_sha256=manifest.source_sha256, status=status,
        pages=manifest.page_count, ocr_detections=manifest.ocr_detections, regions=manifest.regions,
        equipment_tags=manifest.equipment_tags, instrument_tags=manifest.instrument_tags,
        manifest_uri=uri, warnings=manifest.warnings,
    )


def page_vision(vision, page):
    """Reuse a completed local-vision result for a byte-identical rendered page.

    A retry after an interrupted run (even a rolled-back version row) never repeats
    finished visual work. This is an artifact beside the OCR JSON, not a checkpoint;
    graph-run durability stays in app.services.durable_execution."""
    from hashlib import sha256
    from app.schemas.pid import VisionEvidence
    image = (settings.data_root / page.source_image_uri).read_bytes()
    key = sha256(image + f"\0{getattr(vision, 'model', '')}\0v1".encode()).hexdigest()
    path = settings.data_root / "processed/pids/vision" / f"{key}.json"
    try:
        stored = VisionEvidence.model_validate_json(path.read_text(encoding="utf-8"))
        return stored.model_copy(update={"page": page.page, "source_image_uri": page.source_image_uri,
                                         "call_count": 0, "latency_ms": 0})
    except (OSError, ValueError):
        pass
    result = vision.analyze(page)
    if result.status == "available":  # Fallbacks are retried; only completed work is reused.
        write_json(path, result.model_dump(mode="json"))
    return result


def process_pid(request, session, ocr=None, vision=None):
    path, source = read_pid_source(request.source_path)
    checksum = source_sha256(source)
    key = int.from_bytes(bytes.fromhex(checksum[:16]), "big", signed=True)
    if not session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}):
        raise IngestionConflict("This source is already being processed; retry later")
    version = session.scalar(select(DocumentVersion).where(DocumentVersion.source_sha256 == checksum))
    if version:
        document = session.get(Document, version.document_id)
        complete = check_duplicate(version, request)
    else:
        complete = False
        document = session.get(Document, request.document_id) if request.document_id else None
        if request.document_id and (document is None or document.document_type != "pid"):
            raise IngestionConflict("document_id must refer to an existing P&ID document")
        if document is None:
            document = Document(
                id=uuid4(), filename=path.name, document_type="pid", source_path=str(path),
                classification=request.access_scope, checksum=checksum, ingestion_status="pid_processing",
            )
            session.add(document)
        version = DocumentVersion(
            id=uuid4(), document_id=document.id, source_sha256=checksum,
            status="pid_processing", chunk_count=0, warnings=[],
            ingestion_metadata={"kind": "pid", "request": request_metadata(request),
                                "source_filename": path.name,
                                "source_uri": path.relative_to(settings.data_root).as_posix()},
        )
        session.add(version)
    manifest_path = settings.data_root / "processed/pids/manifests" / f"{version.id}.json"
    manifest_uri = manifest_path.relative_to(settings.data_root).as_posix()
    if complete and manifest_path.is_file():
        manifest = PIDManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        artifacts = [manifest.ocr_json_uri, manifest.region_json_uri]
        artifacts += [uri for page in manifest.pages for uri in (page.source_image_uri, page.processed_image_uri)]
        if all((settings.data_root / uri).is_file() for uri in artifacts):
            return manifest_response(manifest, manifest_uri, "duplicate")
    version.status = "pid_processing"
    session.flush()
    try:
        from app.services.local_vision import LocalVisionAdapter
        from app.services.pid_fusion import overlaps
        vision = vision or LocalVisionAdapter()
        visual_pages = []
        pages = []
        detections = []
        ocr = ocr or get_paddle_ocr()
        for page in render_pages(source, path.suffix.lower(), version.id, request.render_dpi, request.preprocessing):
            pages.append(page)
            detections.extend(next(ocr.recognize_pages([page])))
            visual_pages.append(page_vision(vision, page))
            if len(detections) > 20_000:
                raise ValueError("Drawing exceeds 20000 OCR detections")
        regions = group_regions(detections, version.id)
        # Attach observations by overlap only; proximity is never process connectivity.
        from app.schemas.pid import OCRRegion
        from uuid import uuid5
        for visual_page in visual_pages:
            for index, candidate in enumerate(visual_page.candidates):
                targets = [r for r in regions if r.page == visual_page.page and overlaps(r.bbox, candidate.bbox)]
                if not targets:
                    targets = [OCRRegion(region_id=uuid5(version.id, f"visual:{visual_page.page}:{index}"),
                        page=visual_page.page, bbox=candidate.bbox, text_items=[], combined_text="", identified_tags={},
                        region_type="annotation_block", source_image_uri=visual_page.source_image_uri)]
                    regions.extend(targets)
                for region in targets:
                    region.visual_candidates.append(candidate)
                    region.visual_model = visual_page.model
        tags = merged_tags(detections)
        warnings = ["OCR-derived labels are evidence, not process topology.",
                    "All extracted tags are unverified OCR candidates; recognition confidence does not verify equipment identity.",
                    "OCR text and spatial proximity do not establish process topology or connectivity."]
        if any(v.status == "unavailable" for v in visual_pages):
            warnings.append("Local vision unavailable; OCR-only evidence retained.")
        if not detections:
            warnings.append("No text was recognized; no OCR content was invented.")
        if any(item.confidence < 0.6 for item in detections):
            warnings.append("Some OCR detections have confidence below 0.60; review against the rendered image.")
        ocr_path = settings.data_root / "processed/pids/ocr_json" / f"{version.id}.json"
        region_path = settings.data_root / "processed/pids/regions" / f"{version.id}.json"
        identity = {"document_id": str(document.id), "document_version_id": str(version.id), "source_sha256": checksum}
        write_json(ocr_path, identity | {"detections": [d.model_dump(mode="json") for d in detections]})
        write_json(region_path, identity | {"regions": [r.model_dump(mode="json") for r in regions]})
        manifest = PIDManifest(
            document_id=document.id, document_version_id=version.id,
            source_filename=version.ingestion_metadata["source_filename"],
            source_uri=version.ingestion_metadata["source_uri"], source_sha256=checksum,
            page_count=len(pages), render_dpi=request.render_dpi if path.suffix.lower() == ".pdf" else None,
            ocr_model=list(OCR_MODELS), processed_at=datetime.now(timezone.utc),
            synthetic=request.synthetic, warnings=warnings, pages=pages, vision=visual_pages,
            operational_metadata={"document_id": str(document.id), "revision": request.revision,
                "regions_processed": len(regions), "ocr_region_count": sum(bool(r.text_items) for r in regions),
                "visual_model_call_count": sum(v.call_count for v in visual_pages),
                "vision_pages_reused": sum(v.status == "available" and v.call_count == 0 for v in visual_pages),
                "candidate_count": sum(len(v.candidates) for v in visual_pages), "verified_count": 0,
                "conflict_count": 0, "selected_local_vision_model": visual_pages[0].model if visual_pages else None,
                "latency_ms": sum(v.latency_ms for v in visual_pages),
                "fallback_used": any(v.status == "unavailable" for v in visual_pages),
                "fallback_reason": sorted({v.fallback_reason for v in visual_pages if v.fallback_reason})},
            ocr_json_uri=ocr_path.relative_to(settings.data_root).as_posix(),
            region_json_uri=region_path.relative_to(settings.data_root).as_posix(),
            ocr_detections=len(detections), regions=len(regions),
            equipment_tags=tags["equipment_tags"], instrument_tags=tags["instrument_tags"],
        )
        write_json(manifest_path, manifest.model_dump(mode="json"))
        version.status = document.ingestion_status = "pid_processed"
        version.warnings = warnings
        document.checksum = checksum
        session.commit()
        return manifest_response(manifest, manifest_uri, "processed")
    except Exception:
        version.status = document.ingestion_status = "pid_failed"
        version.warnings = ["P&ID processing failed. Resolve the input/dependency issue and retry the same request."]
        session.commit()
        raise
