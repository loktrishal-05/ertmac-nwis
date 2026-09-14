"""Evidence-only retrieval. Citations are copied exclusively from stored chunks."""
from sqlalchemy import select
from app.db.models.document_version import DocumentVersion
from app.schemas.knowledge import ChunkMetadata, Citation, RetrievedChunk, RetrieveResponse
from app.services.tags import extract_tags
from app.services.embeddings import get_embeddings
from app.services.qdrant_service import get_qdrant


def citation_result(metadata: ChunkMetadata, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=metadata.chunk_id, document_id=metadata.document_id,
        document_version_id=metadata.document_version_id, score=score, content=metadata.content,
        citation=Citation(
            title=metadata.title, source_filename=metadata.source_filename,
            source_uri=metadata.source_uri, source_sha256=metadata.source_sha256,
            revision=metadata.revision, section_path=metadata.section_path,
            page_start=metadata.page_start, page_end=metadata.page_end,
            quote=metadata.content, bounding_boxes=metadata.bounding_boxes,
        ),
    )


def retrieve(request, session, embeddings=None, qdrant=None):
    identifiers = extract_tags(request.query)
    ready = session.scalars(select(DocumentVersion.id).where(DocumentVersion.status == "indexed")).all()
    if not ready:
        return RetrieveResponse(query=request.query, detected_identifiers=identifiers, results=[])
    embeddings = embeddings or get_embeddings()
    qdrant = qdrant or get_qdrant()
    qdrant.initialize()
    filters = request.filters.model_dump(mode="json")
    if filters["document_version_id"] and filters["document_version_id"] not in {str(v) for v in ready}:
        return RetrieveResponse(query=request.query, detected_identifiers=identifiers, results=[])
    # Exact detected identifiers constrain matches unless explicit tag filters were supplied.
    for key in ("equipment_tags", "instrument_tags"):
        if not filters[key] and identifiers[key]:
            filters[key] = identifiers[key]
    if not filters["document_version_id"]:
        filters["document_version_id"] = [str(v) for v in ready]
    points = qdrant.search(embeddings.embed([request.query], query=True)[0], request.top_k, filters)
    results = []
    for point in points:
        metadata = ChunkMetadata.model_validate(point.payload)
        if str(point.id) != str(metadata.chunk_id):
            raise RuntimeError("Stored chunk ID mismatch; refusing invalid citation")
        results.append(citation_result(metadata, point.score))
    return RetrieveResponse(query=request.query, detected_identifiers=identifiers, results=results)
