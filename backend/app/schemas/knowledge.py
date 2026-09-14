"""Validated citation-ready evidence contracts."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, model_validator


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_path: str = Field(min_length=1, max_length=500, description="PDF path relative to data/raw")
    document_id: UUID | None = None
    document_type: Literal["sop", "incident", "other"] = "sop"
    title: str = Field(min_length=1, max_length=200)
    revision: str | None = Field(default=None, max_length=100)
    document_date: date | None = None
    effective_date: date | None = None
    facility_id: str | None = Field(default=None, max_length=100)
    unit_id: str | None = Field(default=None, max_length=100)
    language: Literal["en"] = "en"
    synthetic: bool = False
    access_scope: str = Field(default="internal", min_length=1, max_length=50)


class BoundingBox(BaseModel):
    page: int = Field(ge=1)
    coordinates: tuple[float, float, float, float]
    origin: Literal["TOPLEFT", "BOTTOMLEFT"]


class ChunkMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0"
    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_type: str
    title: str
    source_filename: str
    source_uri: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mime_type: Literal["application/pdf"] = "application/pdf"
    facility_id: str | None
    unit_id: str | None
    equipment_tags: list[str]
    instrument_tags: list[str]
    line_numbers: list[str]
    section_path: list[str]
    section_title: str | None
    chunk_index: int = Field(ge=0)
    content: str = Field(min_length=1)
    content_type: str
    token_count: int = Field(ge=1, le=500)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    bounding_boxes: list[BoundingBox]
    document_date: date | None
    revision: str | None
    effective_date: date | None
    language: str
    synthetic: bool
    extraction_method: str
    ocr_engine: str | None = None
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)
    extraction_quality: str
    pipeline_version: str = "3a.1"
    access_scope: str
    ingested_at: datetime

    @model_validator(mode="after")
    def check_provenance(self):
        if self.page_end < self.page_start:
            raise ValueError("Invalid page range")
        if any(not self.page_start <= box.page <= self.page_end for box in self.bounding_boxes):
            raise ValueError("Bounding box outside chunk page range")
        return self


class RetrievalFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: str | None = None
    document_id: UUID | None = None
    document_version_id: UUID | None = None
    facility_id: str | None = None
    unit_id: str | None = None
    synthetic: bool | None = None
    access_scope: str | None = None
    language: str | None = None
    equipment_tags: list[str] = Field(default_factory=list)
    instrument_tags: list[str] = Field(default_factory=list)


class RetrieveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=6, ge=1, le=30)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)


class Citation(BaseModel):
    title: str
    source_filename: str
    source_uri: str
    source_sha256: str
    revision: str | None
    section_path: list[str]
    page_start: int
    page_end: int
    quote: str
    bounding_boxes: list[BoundingBox]


class RetrievedChunk(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    score: float
    content: str
    citation: Citation


class RetrieveResponse(BaseModel):
    query: str
    detected_identifiers: dict[str, list[str]]
    results: list[RetrievedChunk]
