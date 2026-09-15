"""Explicit OCR text indexing; never infer labels-to-symbols or topology."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid5
import json
from sqlalchemy import text
from app.core.config import settings
from app.db.models.document_version import DocumentVersion
from app.schemas.pid import PIDManifest, OCRRegion
from app.schemas.knowledge import ChunkMetadata
from app.services.extraction import Block, source_sha256
from app.services.chunking import Chunker
from app.services.embeddings import get_embeddings
from app.services.qdrant_service import get_qdrant
from app.services.pid_images import read_pid_source
from app.services.ingestion import IngestionConflict


def artifact(uri):
    path = (settings.data_root / uri).resolve()
    root = (settings.data_root / "processed/pids").resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Missing or invalid P&ID artifact path")
    return path


def region_chunks(manifest, regions, request_metadata, tokenizer):
    chunks = []
    for region in regions:
        if not region.combined_text.strip() or not any(c.isalnum() for c in region.combined_text):
            continue
        if region.page > manifest.page_count or any(d.page != region.page or d.source_image != region.source_image_uri for d in region.text_items):
            raise ValueError("Region has inconsistent page/image provenance")
        if region.source_image_uri != manifest.pages[region.page - 1].source_image_uri:
            raise ValueError("Region source differs from manifest")
        if region.combined_text != "\n".join(d.text for d in region.text_items) or not region.text_items:
            raise ValueError("Region text must equal its stored OCR items")
        boxes = [{"page": region.page, "coordinates": d.bbox, "origin": "TOPLEFT"} for d in region.text_items]
        block = Block(text=region.combined_text, section_path=[f"OCR region {region.region_id}"],
                      page_start=region.page, page_end=region.page, bounding_boxes=boxes, content_type="pid_region_text")
        for index, chunk in enumerate(Chunker(tokenizer).chunk([block], request_metadata["title"])):
            confidence = min(d.confidence for d in region.text_items)
            chunks.append(ChunkMetadata(
                chunk_id=uuid5(manifest.document_version_id, f"pid:{region.region_id}:{index}"),
                document_id=manifest.document_id, document_version_id=manifest.document_version_id,
                document_type="pid", title=request_metadata["title"], source_filename=manifest.source_filename,
                source_uri=manifest.source_uri, source_sha256=manifest.source_sha256,
                mime_type="application/pdf" if Path(manifest.source_filename).suffix.lower() == ".pdf" else "image/png" if Path(manifest.source_filename).suffix.lower() == ".png" else "image/jpeg",
                facility_id=None, unit_id=None, equipment_tags=region.identified_tags.get("equipment_tags", []),
                instrument_tags=region.identified_tags.get("instrument_tags", []), line_numbers=region.identified_tags.get("line_numbers", []),
                section_path=chunk.section_path, section_title=chunk.section_path[-1], chunk_index=len(chunks),
                content=chunk.content, content_type="pid_region_text", token_count=chunk.token_count,
                page_start=region.page, page_end=region.page, page=region.page, bounding_boxes=boxes,
                document_date=None, revision=request_metadata.get("revision"), effective_date=None,
                language="en", synthetic=manifest.synthetic, extraction_method="paddleocr_ppocrv5",
                ocr_engine="paddleocr_ppocrv5", ocr_confidence=confidence, ocr_derived=True,
                extraction_quality="low_confidence_ocr" if confidence < 0.6 else "unverified_ocr",
                pipeline_version="3b2.1", access_scope=request_metadata["access_scope"],
                ingested_at=datetime.now(timezone.utc), region_id=region.region_id, source_image_uri=region.source_image_uri,
            ))
    return chunks


def index_pid(version_id, session, embeddings=None, qdrant=None):
    if not session.scalar(text("SELECT pg_try_advisory_xact_lock_shared(3302001)")):
        raise IngestionConflict("Retrieval migration is active; retry later")
    version = session.get(DocumentVersion, version_id)
    if version is None or version.ingestion_metadata.get("kind") != "pid" or version.status not in ("pid_processed", "pid_indexed", "pid_index_failed"):
        raise ValueError("Expected an existing processed P&ID version")
    key = int.from_bytes(bytes.fromhex(version.source_sha256[:16]), "big", signed=True)
    if not session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}):
        raise IngestionConflict("P&ID version is busy; retry later")
    manifest = PIDManifest.model_validate_json(artifact(f"processed/pids/manifests/{version_id}.json").read_text(encoding="utf-8"))
    if manifest.document_version_id != version.id or manifest.document_id != version.document_id or manifest.source_sha256 != version.source_sha256:
        raise ValueError("P&ID manifest identity mismatch")
    source_uri = Path(manifest.source_uri)
    try:
        relative = source_uri.relative_to("raw/pids/source")
    except ValueError as error:
        raise ValueError("Invalid P&ID source URI") from error
    _, source = read_pid_source(str(relative))
    if source_sha256(source) != manifest.source_sha256:
        raise IngestionConflict("P&ID source has changed; existing evidence preserved")
    qdrant = qdrant or get_qdrant()
    qdrant.initialize()
    if version.status == "pid_indexed":
        count = qdrant.client.count(qdrant.collection, count_filter=qdrant.filter({"document_version_id": str(version.id)})).count
        if count == version.chunk_count:
            return {"document_version_id": str(version.id), "status": "duplicate", "chunk_count": count, "ocr_derived": True}
    raw = json.loads(artifact(manifest.region_json_uri).read_text(encoding="utf-8"))
    if raw["document_version_id"] != str(version.id) or raw["source_sha256"] != version.source_sha256:
        raise ValueError("Region artifact identity mismatch")
    regions = [OCRRegion.model_validate(r) for r in raw["regions"]]
    embeddings = embeddings or get_embeddings()
    chunks = region_chunks(manifest, regions, version.ingestion_metadata["request"], embeddings.tokenizer)
    if not chunks:
        raise ValueError("No useful OCR text to index")
    version.status = "pid_indexing"
    session.flush()
    try:
        qdrant.delete_version(version.id)
        for offset in range(0, len(chunks), 16):
            batch = chunks[offset:offset + 16]
            qdrant.upsert(batch, embeddings.embed([c.content for c in batch]))
        version.status = "pid_indexed"
        version.chunk_count = len(chunks)
        session.commit()
    except Exception:
        version.status = "pid_index_failed"
        session.commit()
        raise
    return {"document_version_id": str(version.id), "status": "indexed", "chunk_count": len(chunks), "ocr_derived": True}
