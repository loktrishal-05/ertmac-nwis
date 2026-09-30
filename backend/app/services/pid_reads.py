"""Authorized P&ID artifact views; all paths are server-derived and version-bound."""
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from app.core.config import settings
from app.db.models import Document, DocumentVersion
from app.schemas.pid import PIDManifest
from app.services.pid_evidence import load_pid_evidence
from app.services.pid_fusion import LIMITATION
from app.services.ui_reads import envelope, now

def query():
    return select(DocumentVersion, Document).join(Document, Document.id == DocumentVersion.document_id).where(
        Document.document_type == "pid", Document.classification == "internal",
        DocumentVersion.ingestion_metadata["kind"].as_string() == "pid",
        DocumentVersion.ingestion_metadata["request"]["access_scope"].as_string() == "internal")

def version(session, ident):
    row = session.execute(query().where(DocumentVersion.id == ident)).one_or_none()
    if row is None:
        raise HTTPException(404, "P&ID not found in authorized scope.")
    return row

def read(relative, directory, maximum=32 * 1024 * 1024):
    root = settings.data_root.resolve()
    requested = Path(relative)
    if requested.is_absolute() or requested.drive or ":" in relative or ".." in requested.parts:
        raise ValueError("Invalid artifact path")
    allowed = root / directory
    path = (root / requested).resolve()
    # Do not resolve the allowed directory: a symlink must not redefine its containment boundary.
    if not path.is_relative_to(allowed) or not path.is_file():
        raise ValueError("Artifact unavailable")
    with path.open("rb") as stream:
        content = stream.read(maximum + 1)
    if len(content) > maximum:
        raise ValueError("Artifact exceeds read limit")
    return content

def manifest(v):
    value = PIDManifest.model_validate_json(read(f"processed/pids/manifests/{v.id}.json", "processed/pids/manifests"))
    if value.document_version_id != v.id or value.document_id != v.document_id or value.source_sha256 != v.source_sha256:
        raise ValueError("Artifact binding mismatch")
    if value.page_count > 10 or value.regions > 21000:
        raise ValueError("Artifact exceeds pipeline limits")
    return value

def summary(v, doc):
    try:
        m = manifest(v)
        pages = m.page_count
    except (ValueError, OSError):
        pages = None
    request = v.ingestion_metadata.get("request", {})
    return {"document_version_id": v.id, "document_id": doc.id,
            "filename": v.ingestion_metadata.get("source_filename", doc.filename),
            "title": request.get("title"), "revision": request.get("revision"),
            "source_sha256": v.source_sha256, "processing_status": v.status,
            "page_count": pages, "artifacts_available": pages is not None, "created_at": v.created_at}

def listing(session, limit, offset):
    rows = session.execute(query().order_by(DocumentVersion.created_at.desc(), DocumentVersion.id.desc())
                           .offset(offset).limit(limit + 1)).all()
    return envelope([summary(v, d) for v, d in rows], limit, offset)

def detail(session, ident, page_number, limit, offset):
    v, doc = version(session, ident)
    try:
        m = manifest(v)
        if page_number > m.page_count:
            raise HTTPException(404, "Page not found.")
        refs = load_pid_evidence(session, ident, page_number=page_number, offset=offset, limit=limit + 1)
        items = []
        for ref in refs:
            value = ref.model_dump(mode="json", exclude={"source_uri", "source_image_uri"})
            for text in value["text_items"]:
                text.pop("source_image", None)
            value["confidence"] = ref.confidence if ref.text_items else None
            value["human_review_required"] = not ref.fusion or any(f.review_required for f in ref.fusion)
            value["conflicts"] = [f.model_dump(mode="json") for f in ref.fusion if f.registry_status == "CONFLICTING"]
            items.append(value)
        return {**summary(v, doc), "as_of": now(), "limitation": LIMITATION,
            "pages": [{"page": p.page, "width": p.width, "height": p.height,
                       "image_url": f"/documents/pid/{ident}/pages/{p.page}/image"} for p in m.pages],
            "selected_page": page_number, "regions": envelope(items, limit, offset)}
    except (ValueError, OSError):
        raise HTTPException(409, "P&ID artifacts unavailable, stale, or inconsistent.") from None

def image(session, ident, page_number):
    v, _ = version(session, ident)
    try:
        m = manifest(v)
        if page_number > m.page_count:
            raise HTTPException(404, "Page not found.")
        page = m.pages[page_number - 1]
        # No query-supplied paths, original uploads, HTML or SVG. Only this version's rendered PNG.
        expected = f"processed/pids/page_images/{ident}/page_{page_number:04d}_rendered.png"
        if page.source_image_uri != expected:
            raise ValueError("Image binding mismatch")
        data = read(expected, f"processed/pids/page_images/{ident}", 128 * 1024 * 1024)
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Invalid image type")
        return Response(data, media_type="image/png", headers={"Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff", "Content-Disposition": 'inline; filename="drawing.png"'})
    except (ValueError, OSError):
        raise HTTPException(409, "P&ID image unavailable or inconsistent.") from None
