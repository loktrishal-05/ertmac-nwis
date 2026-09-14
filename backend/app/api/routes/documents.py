"""Document ingestion placeholder; no files are accepted or stored."""

from fastapi import APIRouter
from app.schemas.document import IngestionResponse

router = APIRouter(tags=["documents"])


@router.post("/documents/ingest", response_model=IngestionResponse)
def ingest_document() -> IngestionResponse:
    return IngestionResponse()
