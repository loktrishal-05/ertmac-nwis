"""Ingestion result contract."""

from typing import Literal
from uuid import UUID
from pydantic import BaseModel


class IngestionResponse(BaseModel):
    document_id: UUID
    document_version_id: UUID
    filename: str
    document_type: str
    status: Literal["indexed", "duplicate", "ocr_required"]
    chunk_count: int
    embedding_model: str
    qdrant_collection: str
    source_sha256: str
    warnings: list[str]
