"""retrieve_documents (hybrid retrieval, 3A/3B2) and get_pid_regions
(P&ID OCR region read, 3B1/3B2). Both wrap an existing READ function only."""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.agents.evidence import document_chunk_evidence
from app.agents.registry import register
from app.schemas.knowledge import RetrieveRequest
from app.services.model_gateway.types import ToolSpec
from app.services.retrieval import retrieve


def _ocr_status(ocr_derived: bool, confidence: float | None) -> str | None:
    # Phase 3B1 rule, reused exactly: confidence < 0.6 is ambiguous; OCR
    # confidence never establishes a "verified" status.
    if not ocr_derived:
        return None
    return "ambiguous" if confidence is not None and confidence < 0.6 else "unverified"


class RetrieveDocumentsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=6, ge=1, le=30)
    document_types: list[str] = Field(default_factory=list, max_length=10)
    access_scope: str = Field(default="internal", min_length=1, max_length=50)


def retrieve_documents(session, arguments: RetrieveDocumentsArguments):
    request = RetrieveRequest(query=arguments.query, top_k=arguments.top_k, document_types=arguments.document_types,
                              filters={"access_scope": arguments.access_scope})
    response = retrieve(request, session)
    refs, results = [], []
    for result in response.results:
        citation = result.citation
        ref = document_chunk_evidence(
            chunk_id=result.chunk_id, document_id=result.document_id, document_version_id=result.document_version_id,
            source_filename=citation.source_filename, source_sha256=citation.source_sha256,
            section_path=citation.section_path, page_start=citation.page_start, page_end=citation.page_end,
            bounding_boxes=[box.model_dump(mode="json") for box in citation.bounding_boxes],
            quote=citation.quote, ocr_derived=citation.ocr_derived, ocr_confidence=citation.ocr_confidence,
            ocr_status=_ocr_status(citation.ocr_derived, citation.ocr_confidence),
            source_uri=citation.source_uri, source_image_uri=citation.source_image_uri,
            region_id=citation.region_id, revision=citation.revision,
        )
        refs.append(ref)
        results.append({"evidence_id": ref.evidence_id, "score": result.score, "content_type": result.content_type})
    payload = {"strategy": response.strategy, "warnings": response.warnings, "results": results}
    return payload, refs


class GetPIDRegionsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_version_id: UUID


def get_pid_regions(session, arguments: GetPIDRegionsArguments):
    # pid_evidence_lookup in the design maps to this existing registered tool.
    from app.services.pid_evidence import load_pid_evidence
    try:
        refs = load_pid_evidence(session, arguments.document_version_id)
    except (ValueError, OSError, KeyError, TypeError) as error:
        return {"regions": [], "warnings": [str(error)]}, []
    return {"region_count": len(refs), "evidence_ids": [ref.evidence_id for ref in refs]}, refs


register(
    ToolSpec(
        name="retrieve_documents",
        description="Read-only hybrid (dense+sparse+rerank) search over indexed SOPs, manuals, incidents, "
                     "and shift logs. Returns citation-ready evidence references, never an answer.",
        parameters=RetrieveDocumentsArguments.model_json_schema(),
    ),
    RetrieveDocumentsArguments, retrieve_documents,
)
register(
    ToolSpec(
        name="get_pid_regions",
        description="Read-only lookup of OCR-derived P&ID regions for an already-processed drawing version. "
                     "OCR confidence never establishes verified equipment identity or process topology.",
        parameters=GetPIDRegionsArguments.model_json_schema(),
    ),
    GetPIDRegionsArguments, get_pid_regions,
)
