"""Measured evidence coverage, never authorization or model confidence."""
from uuid import UUID
from types import SimpleNamespace
import re
from sqlalchemy import select
from pydantic import TypeAdapter
from app.agents.evidence import EvidenceRef
from app.agents.citations import validate_citations
from app.schemas.agent_outputs import Citation
from app.db.models import Document, DocumentVersion
from app.services import evidence_integrity as integrity


def refs_as_models(refs):
    return [TypeAdapter(EvidenceRef).validate_python(r) for r in refs]


def source_valid(session, ref, scope="internal"):
    try:
        if ref.kind == "document_chunk" and not ref.ocr_derived:
            from app.services.verified_knowledge import resolve_sources
            fresh, _ = resolve_sources(session, [UUID(ref.chunk_id)], scope)
            return fresh[0] == ref.model_dump(mode="json")
        if ref.kind in ("document_chunk", "pid_region"):
            version = session.get(DocumentVersion, UUID(ref.document_version_id))
            doc = session.get(Document, UUID(ref.document_id))
            if (not version or not doc or doc.classification != scope or version.status not in ("indexed", "pid_processed", "pid_indexed")
                    or doc.ingestion_status not in ("indexed", "pid_processed", "pid_indexed") or doc.checksum != ref.source_sha256
                    or version.document_id != doc.id):
                return False
            if session.scalar(select(DocumentVersion.id).where(DocumentVersion.document_id == doc.id,
                    DocumentVersion.id != version.id, DocumentVersion.created_at >= version.created_at).limit(1)):
                return False
        if ref.kind == "pid_region":
            from app.services.pid_evidence import load_pid_evidence
            return any(fresh == ref for fresh in load_pid_evidence(session, UUID(ref.document_version_id)))
        if ref.kind == "document_chunk" and ref.ocr_derived:
            return False  # OCR chunk snapshots alone cannot establish current region provenance.
        data = ref.model_dump(mode="json")
        content_hash, provenance, _ = integrity._item_content(session, ref.kind, data)
        if ref.kind == "sensor_window" and not provenance.get("citations"):
            return False
        return integrity._reverify_against_source(session, SimpleNamespace(evidence_type=ref.kind,
            source_hash=ref.source_sha256, content_hash=content_hash, provenance=provenance))[0]
    except Exception:
        return False  # Unavailable source cannot increase measured sufficiency.


def requirements(query):
    required = set()
    for pattern, category in ((r"sensor|vibration|temperature|pressure", "sensor"),
                              (r"maintenance|history", "maintenance"),
                              (r"p&?id|drawing|ocr", "pid"),
                              (r"sop", "sop"), (r"incident", "incident"),
                              (r"manual|document|procedure", "document")):
        if re.search(pattern, query, re.I): required.add(category)
    # Static documented limits do not assert current sensor conditions.
    if re.match(r"what is the documented", query, re.I): required.discard("sensor")
    return required or {"document"}


def assess(query, refs, *, invalid_ids=(), tool_failed=False, citations=(), multi_document=False, categories=None):
    refs = refs_as_models(refs)
    usable = [r for r in refs if r.evidence_id not in invalid_ids and r.locator and r.source_sha256]
    present = set()
    for r in usable:
        present.add({"document_chunk": "document", "pid_region": "pid", "sensor_window": "sensor", "csv_row": "structured_record"}[r.kind])
        present.update((categories or {}).get(r.evidence_id, []))
    missing = sorted(requirements(query) - present)
    if multi_document and len({getattr(r, "document_id", None) for r in usable if getattr(r, "document_id", None)}) < 2:
        missing.append("multiple_documents")
    issues = []
    if invalid_ids or len(usable) != len(refs): issues.append("invalid_or_unavailable_source")
    if tool_failed: issues.append("tool_or_retrieval_failure")
    try:
        checked = [Citation.model_validate(c) for c in citations]
        if not validate_citations(emitted=[c.evidence_id for c in checked], available=usable,
                                  citations=checked, require_citations=True).valid:
            issues.append("missing_or_invalid_citation")
    except Exception:
        issues.append("missing_or_invalid_citation")
    critical = not usable or bool(set(missing) & {"sensor", "pid"}) or (tool_failed and not present)
    status = "INSUFFICIENT" if critical else ("PARTIAL" if missing or issues else "SUFFICIENT")
    return {"state": status, "missing_categories": missing, "issues": issues,
            "valid_evidence_count": len(usable), "required_categories": sorted(requirements(query)),
            "meaning": "Evidence coverage only; never permission to execute."}


def categories_for(session, refs):
    result = {}
    for r in refs:
        try:
            if r.kind == "document_chunk":
                doc = session.get(Document, UUID(r.document_id))
                if doc: result[r.evidence_id] = [doc.document_type]
            elif r.kind == "csv_row":
                table, _ = integrity._lookup_csv_row(session, r.source_sha256, r.source_row_number)
                result[r.evidence_id] = ["maintenance"] if table == "maintenance_records" else (["sensor"] if table == "sensor_readings" else [])
        except Exception:
            pass
    return result
