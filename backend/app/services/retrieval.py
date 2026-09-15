"""Evidence-only retrieval. Citations are copied exclusively from stored chunks."""
from sqlalchemy import select
from time import perf_counter
from app.core.config import settings
from app.db.models.document_version import DocumentVersion
from app.schemas.knowledge import ChunkMetadata, Citation, RetrievedChunk, RetrieveResponse
from app.services.sparse import identifiers as extract_identifiers
from app.services.pid_identifiers import normalize_identifier
from app.services.ranking import fuse, deduplicate
from app.services.reranking import get_reranker
from app.services.embeddings import get_embeddings
from app.services.qdrant_service import get_qdrant


def citation_result(metadata: ChunkMetadata, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=metadata.chunk_id, document_id=metadata.document_id,
        document_version_id=metadata.document_version_id, score=score, content=metadata.content,
        content_type=metadata.content_type,
        citation=Citation(
            title=metadata.title, source_filename=metadata.source_filename,
            source_uri=metadata.source_uri, source_sha256=metadata.source_sha256,
            revision=metadata.revision, section_path=metadata.section_path,
            page_start=metadata.page_start, page_end=metadata.page_end,
            quote=metadata.content, bounding_boxes=metadata.bounding_boxes,
            ocr_derived=metadata.ocr_derived, ocr_confidence=metadata.ocr_confidence,
            region_id=metadata.region_id, source_image_uri=metadata.source_image_uri,
        ),
    )


def retrieve(request, session, embeddings=None, qdrant=None, reranker=None):
    started = perf_counter()
    timings = dict.fromkeys(("dense_embedding", "dense_search", "sparse_search", "rrf_fusion", "reranking", "deduplication"), 0.0)
    strategy = request.strategy or ("hybrid_rerank" if settings.reranking_enabled else "hybrid")
    if not settings.sparse_retrieval_enabled:
        if request.strategy in ("sparse", "hybrid", "hybrid_rerank"):
            raise ValueError("Sparse retrieval is disabled by configuration")
        strategy = "dense"
    if strategy == "hybrid_rerank" and not settings.reranking_enabled:
        raise ValueError("Reranking is disabled by configuration")
    query = normalize_identifier(request.query)
    identifiers = extract_identifiers(query)
    ready = session.scalars(select(DocumentVersion.id).where(DocumentVersion.status.in_(["indexed", "pid_indexed"]))).all()
    response = RetrieveResponse(query=request.query, strategy={"hybrid": "dense_sparse_rrf", "hybrid_rerank": "dense_sparse_rrf_rerank"}.get(strategy, strategy),
                                detected_identifiers=identifiers, results=[], timings_ms=timings)
    if not ready:
        response.timings_ms["total"] = (perf_counter() - started) * 1000
        return response
    qdrant = qdrant or get_qdrant()
    qdrant.initialize(require_sparse=strategy != "dense")
    filters = request.filters.model_dump(mode="json")
    for key in ("equipment_tags", "instrument_tags", "facility_id", "unit_id"):
        if getattr(request, key):
            filters[key] = getattr(request, key)
    if request.document_types:
        filters["document_type"] = request.document_types
    for key in ("equipment_tags", "instrument_tags"):
        filters[key] = [normalize_identifier(tag) for tag in filters[key]]
    if filters["document_version_id"] and filters["document_version_id"] not in {str(v) for v in ready}:
        return response
    # Detected terms strengthen sparse scoring; only explicit user filters constrain scope.
    if not filters["document_version_id"]:
        filters["document_version_id"] = [str(v) for v in ready]
    dense, sparse = [], []
    if strategy != "sparse":
        embeddings = embeddings or get_embeddings()
        tick = perf_counter()
        vector = embeddings.embed([query], query=True)[0]
        timings["dense_embedding"] = (perf_counter() - tick) * 1000
        tick = perf_counter()
        dense = qdrant.search(vector, settings.dense_top_k, filters)
        timings["dense_search"] = (perf_counter() - tick) * 1000
    if strategy != "dense":
        tick = perf_counter()
        sparse = qdrant.sparse_search(query, settings.sparse_top_k, filters)
        timings["sparse_search"] = (perf_counter() - tick) * 1000
        if identifiers["technical_identifiers"] and not sparse:
            response.warnings.append("No lexical evidence matched the query; dense neighbors, if returned, do not establish the requested identifier exists.")
    tick = perf_counter()
    candidates = fuse(dense, sparse)
    timings["rrf_fusion"] = (perf_counter() - tick) * 1000
    for item in candidates:
        point = item["point"]
        metadata = ChunkMetadata.model_validate(point.payload)
        if str(point.id) != str(metadata.chunk_id):
            raise RuntimeError("Stored chunk ID mismatch; refusing invalid citation")
        item["metadata"] = metadata
    if strategy == "hybrid_rerank" and candidates:
        tick = perf_counter()
        head = candidates[:settings.rerank_top_k]
        scores = (reranker or get_reranker()).score(request.query, [c["metadata"].title + "\n" + c["metadata"].content for c in head])
        if len(scores) != len(head):
            raise RuntimeError("Reranker result count mismatch")
        for item, score in zip(head, scores):
            item["rerank_score"] = score
        candidates = sorted(head, key=lambda c: (-c["rerank_score"], -c["fusion_score"], str(c["point"].id))) + candidates[len(head):]
        if request.top_k > len(head) and len(candidates) > len(head):
            response.warnings.append("Requested top_k exceeds reranked candidates; remaining results retain fused order and null rerank_score.")
        timings["reranking"] = (perf_counter() - tick) * 1000
    tick = perf_counter()
    candidates, warnings = deduplicate(candidates, explicit_version=request.filters.document_version_id is not None)
    response.warnings.extend(warnings)
    timings["deduplication"] = (perf_counter() - tick) * 1000
    for item in candidates[:request.top_k]:
        metadata = item["metadata"]
        score = item["point"].score if strategy in ("dense", "sparse") else item["rerank_score"] if item["rerank_score"] is not None else item["fusion_score"]
        result = citation_result(metadata, score)
        for name in ("dense_rank", "sparse_rank", "fusion_score", "rerank_score"):
            setattr(result, name, item[name])
        response.results.append(result)
    if any(r.citation.ocr_derived for r in response.results):
        response.warnings.append("OCR-derived labels are unverified evidence, not process topology.")
    if any(r.citation.ocr_confidence is not None and r.citation.ocr_confidence < 0.6 for r in response.results):
        response.warnings.append("Low-confidence OCR evidence is present; inspect the stored source image.")
    timings["total"] = (perf_counter() - started) * 1000
    response.timings_ms = timings
    return response
