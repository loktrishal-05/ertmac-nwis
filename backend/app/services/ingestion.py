"""Synchronous prototype ingestion with checksum locks and retryable state."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4, uuid5
import json

from sqlalchemy import select, text
from app.core.config import settings
from app.db.models.document import Document
from app.db.models.document_version import DocumentVersion
from app.schemas.document import IngestionResponse
from app.schemas.knowledge import ChunkMetadata, IngestRequest
from app.services.extraction import extract_pdf, source_sha256
from app.services.chunking import Chunker
from app.services.tags import extract_tags
from app.services.embeddings import get_embeddings
from app.services.qdrant_service import get_qdrant


class IngestionConflict(ValueError):
    pass


def resolve_source(relative: str) -> Path:
    root = (settings.data_root / "raw").resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() != ".pdf" or not path.is_file():
        raise ValueError("source_path must identify an existing PDF inside data/raw")
    if not 0 < path.stat().st_size <= 20 * 1024 * 1024:
        raise ValueError("PDF size must be between 1 byte and 20 MiB")
    return path


def duplicate_matches(version, request):
    incoming = request.model_dump(mode="json", exclude={"source_path", "document_id"})
    stored = {key: value for key, value in version.ingestion_metadata.items()
              if key not in ("source_filename", "source_uri")}
    if stored != incoming:
        raise IngestionConflict("This source SHA-256 already exists with different metadata")
    if request.document_id and request.document_id != version.document_id:
        raise IngestionConflict("This source already belongs to another document")
    return version.status in ("indexed", "ocr_required")


def ingestion_result(version, document, status=None):
    return IngestionResponse(
        document_id=document.id, document_version_id=version.id,
        filename=version.ingestion_metadata.get("source_filename", document.filename),
        document_type=version.ingestion_metadata["document_type"], status=status or version.status,
        chunk_count=version.chunk_count, embedding_model=settings.embedding_model,
        qdrant_collection=settings.qdrant_collection, source_sha256=version.source_sha256,
        warnings=version.warnings,
    )


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def ingest(request: IngestRequest, session, embeddings=None, qdrant=None):
    if not session.scalar(text("SELECT pg_try_advisory_xact_lock_shared(3302001)")):
        raise IngestionConflict("Retrieval index migration is in progress; retry ingestion later")
    path = resolve_source(request.source_path)
    # Read once: extraction and hashing operate on the same immutable byte snapshot.
    source = path.read_bytes()
    if len(source) > 20 * 1024 * 1024 or not source.startswith(b"%PDF-"):
        raise ValueError("Not a supported PDF")
    checksum = source_sha256(source)
    lock_key = int(checksum[:16], 16)
    if lock_key >= 2**63:
        lock_key -= 2**64
    acquired = session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": lock_key})
    if not acquired:
        raise IngestionConflict("This source is already being ingested; retry later")
    version = session.scalar(select(DocumentVersion).where(DocumentVersion.source_sha256 == checksum))
    if version:
        document = session.get(Document, version.document_id)
        if duplicate_matches(version, request):
            return ingestion_result(version, document, "duplicate" if version.status == "indexed" else "ocr_required")
    else:
        document = session.get(Document, request.document_id) if request.document_id else None
        if request.document_id and document is None:
            raise ValueError("Unknown document_id")
        if document is None:
            document = Document(
                id=uuid4(), filename=path.name, document_type=request.document_type,
                source_path=str(path), classification=request.access_scope,
                checksum=checksum, ingestion_status="processing",
            )
            session.add(document)
        version = DocumentVersion(
            id=uuid4(), document_id=document.id, source_sha256=checksum, status="processing",
            chunk_count=0, warnings=[],
            ingestion_metadata={
                **request.model_dump(mode="json", exclude={"source_path", "document_id"}),
                "source_filename": path.name,
                "source_uri": path.relative_to(settings.data_root).as_posix(),
            },
        )
        session.add(version)
    session.flush()
    extraction = extract_pdf(source)
    version.warnings = extraction.report["warnings"]
    base = settings.data_root / "processed" / "documents"
    key = str(version.id)
    write_json(base / "extraction_reports" / f"{key}.json", extraction.report)
    write_json(base / "structured_json" / f"{key}.json", extraction.structured)
    markdown_path = base / "markdown" / f"{key}.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(extraction.markdown, encoding="utf-8")
    if extraction.status == "ocr_required":
        version.status = document.ingestion_status = "ocr_required"
        session.commit()
        return ingestion_result(version, document)

    embeddings = embeddings or get_embeddings()
    qdrant = qdrant or get_qdrant()
    try:
        chunks = Chunker(embeddings.tokenizer).chunk(extraction.blocks, request.title)
        if not chunks:
            raise ValueError("No usable chunks extracted")
        metadata = []
        common = request.model_dump(exclude={"source_path", "document_id"})
        for index, chunk in enumerate(chunks):
            metadata.append(ChunkMetadata(
                **common, chunk_id=uuid5(version.id, str(index)),
                document_id=document.id, document_version_id=version.id,
                source_filename=path.name, source_uri=path.relative_to(settings.data_root).as_posix(),
                source_sha256=checksum, **extract_tags(chunk.content),
                section_path=chunk.section_path,
                section_title=chunk.section_path[-1] if chunk.section_path else None,
                chunk_index=index, content=chunk.content, content_type=chunk.content_type,
                token_count=chunk.token_count, page_start=chunk.page_start, page_end=chunk.page_end,
                bounding_boxes=chunk.bounding_boxes, extraction_method=extraction.report["extraction_method"],
                extraction_quality=extraction.report["extraction_quality"], ingested_at=datetime.now(timezone.utc),
            ))
        qdrant.initialize()
        # Remove only this retry's version points. Other documents/revisions are untouched.
        qdrant.delete_version(version.id)
        for offset in range(0, len(chunks), 16):
            vectors = embeddings.embed([c.embedding_text for c in chunks[offset:offset + 16]])
            qdrant.upsert(metadata[offset:offset + 16], vectors)
        write_json(settings.data_root / "indexes" / "ingestion_manifests" / f"{key}.json", {
            "document_version_id": key, "source_sha256": checksum,
            "embedding_model": settings.embedding_model, "qdrant_collection": qdrant.collection,
            "chunks": [m.model_dump(mode="json") for m in metadata],
        })
        version.status = document.ingestion_status = "indexed"
        version.chunk_count = len(chunks)
        document.checksum = checksum
        session.commit()
        return ingestion_result(version, document)
    except Exception:
        # PostgreSQL is the visibility authority; partial Qdrant writes are never returned.
        version.status = document.ingestion_status = "failed"
        version.warnings = version.warnings + ["Ingestion failed; retry the same source and metadata after resolving the dependency."]
        session.commit()
        raise
