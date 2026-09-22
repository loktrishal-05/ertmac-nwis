"""EvidenceRef: one type, four kinds, unifying Phase 3A/3B2 chunk citations,
P&ID OCR regions, and Phase 3C CSV rows/sensor windows into a single
deterministic provenance record the citation validator checks against.

evidence_id is ALWAYS derived from stable provenance via SHA-256 — never
hash() or id(), which are per-process and would make identical evidence
produce a different id on every run. Each variant hashes its own most
specific stable identifier (chunk_id, region_id, source_row_number, or
citation_label) alongside kind + source_sha256, not the human-readable
`locator` string alone — two distinct chunks on the same page would
otherwise collide on a locator like "page 3"."""
import hashlib
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field
from app.schemas.pid import OCRDetection


def make_evidence_id(kind: str, source_sha256: str, stable_key: str) -> str:
    digest = hashlib.sha256(f"{kind}:{source_sha256}:{stable_key}".encode("utf-8")).hexdigest()
    return f"{kind}_{digest[:16]}"


class _EvidenceBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    source_filename: str
    source_sha256: str
    locator: str
    source_uri: str | None = None


class DocumentChunkEvidence(_EvidenceBase):
    kind: Literal["document_chunk"] = "document_chunk"
    document_id: str
    document_version_id: str
    chunk_id: str
    section_path: list[str]
    page_start: int
    page_end: int
    bounding_boxes: list[dict]
    quote: str
    ocr_derived: bool = False
    ocr_confidence: float | None = None
    ocr_status: Literal["unverified", "ambiguous"] | None = None
    source_image_uri: str | None = None
    region_id: str | None = None
    revision: str | None = None


class PIDRegionEvidence(_EvidenceBase):
    kind: Literal["pid_region"] = "pid_region"
    document_id: str
    document_version_id: str
    region_id: str
    page: int
    bbox: tuple[float, float, float, float]
    confidence: float
    ocr_status: Literal["unverified", "ambiguous"]
    combined_text: str
    source_image_uri: str | None = None
    revision: str | None = None
    ocr_derived: Literal[True] = True
    text_items: list[OCRDetection] = Field(default_factory=list)
    ocr_region_hash: str | None = None


class CSVRowEvidence(_EvidenceBase):
    kind: Literal["csv_row"] = "csv_row"
    source_row_number: int


class SensorWindowEvidence(_EvidenceBase):
    kind: Literal["sensor_window"] = "sensor_window"
    citation_label: str
    provenance: list[dict]


EvidenceRef = Union[DocumentChunkEvidence, PIDRegionEvidence, CSVRowEvidence, SensorWindowEvidence]


def document_chunk_evidence(*, chunk_id, document_id, document_version_id, source_filename, source_sha256,
                             section_path, page_start, page_end, bounding_boxes, quote,
                             ocr_derived=False, ocr_confidence=None, ocr_status=None, source_uri=None,
                             source_image_uri=None, region_id=None, revision=None) -> DocumentChunkEvidence:
    locator = f"page {page_start}" if page_start == page_end else f"pages {page_start}-{page_end}"
    return DocumentChunkEvidence(
        evidence_id=make_evidence_id("document_chunk", source_sha256, str(chunk_id)),
        source_filename=source_filename, source_sha256=source_sha256, locator=locator, source_uri=source_uri,
        document_id=str(document_id), document_version_id=str(document_version_id), chunk_id=str(chunk_id),
        section_path=section_path, page_start=page_start, page_end=page_end, bounding_boxes=bounding_boxes,
        quote=quote, ocr_derived=ocr_derived, ocr_confidence=ocr_confidence, ocr_status=ocr_status,
        source_image_uri=source_image_uri, region_id=str(region_id) if region_id else None, revision=revision,
    )


def pid_region_evidence(*, region_id, document_id, document_version_id, source_filename, source_sha256,
                         page, bbox, confidence, ocr_status, combined_text, source_image_uri=None, revision=None,
                         source_uri=None, text_items=None, ocr_region_hash=None) -> PIDRegionEvidence:
    locator = f"drawing {document_id} ({source_filename}), revision {revision or 'unknown'}, region {region_id} page {page}"
    key = f"{document_version_id}:{region_id}:{ocr_region_hash}" if ocr_region_hash else str(region_id)
    return PIDRegionEvidence(
        evidence_id=make_evidence_id("pid_region", source_sha256, key),
        source_filename=source_filename, source_sha256=source_sha256, locator=locator, source_uri=source_uri,
        document_id=str(document_id), document_version_id=str(document_version_id), region_id=str(region_id),
        page=page, bbox=bbox, confidence=confidence, ocr_status=ocr_status, combined_text=combined_text,
        source_image_uri=source_image_uri, revision=revision,
        text_items=text_items or [], ocr_region_hash=ocr_region_hash,
    )


def csv_row_evidence(*, source_filename, source_sha256, source_row_number) -> CSVRowEvidence:
    return CSVRowEvidence(
        evidence_id=make_evidence_id("csv_row", source_sha256, str(source_row_number)),
        source_filename=source_filename, source_sha256=source_sha256, locator=f"row {source_row_number}",
        source_row_number=source_row_number,
    )


def sensor_window_evidence(*, source_filename, source_sha256, citation_label, provenance) -> SensorWindowEvidence:
    return SensorWindowEvidence(
        evidence_id=make_evidence_id("sensor_window", source_sha256, citation_label),
        source_filename=source_filename, source_sha256=source_sha256, locator=citation_label,
        citation_label=citation_label, provenance=provenance,
    )
