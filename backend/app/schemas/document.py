"""Ingestion placeholder contract."""

from typing import Literal
from pydantic import BaseModel


class IngestionResponse(BaseModel):
    status: Literal["not_implemented"] = "not_implemented"
    message: str = "Document ingestion will be implemented in the RAG phase."
