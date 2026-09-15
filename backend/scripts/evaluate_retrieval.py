"""Compare four local retrieval strategies against separate synthetic judgments."""
import json
import hashlib
import platform
from datetime import datetime, timezone
from importlib.metadata import version
from statistics import mean
from app.core.config import settings
from app.db.session import SessionLocal
from app.schemas.knowledge import RetrieveRequest, RetrievalFilters
from app.services.retrieval import retrieve
from app.services.retrieval_metrics import metrics, aggregate
from app.services.sparse import ENCODING
from app.services.qdrant_service import get_qdrant
from scripts.prepare_retrieval_eval import SCOPE


def main():
    import torch
    root = settings.data_root / "evaluation"
    questions = [json.loads(line) for line in (root / "retrieval_questions.jsonl").read_text().splitlines() if line.strip()]
    expected = {c["question_id"]: c["citations"] for c in (json.loads(line) for line in (root / "expected_citations.jsonl").read_text().splitlines() if line.strip())}
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "dataset": "synthetic-retrieval-v1",
              "sparse_encoding": ENCODING, "dense_model": settings.embedding_model, "reranker_model": settings.reranker_model,
              "settings": {k: getattr(settings, k) for k in ("dense_top_k", "sparse_top_k", "rerank_top_k", "final_context_k")},
              "system": {"platform": platform.platform(), "processor": platform.processor(), "paddleocr": version("paddleocr"), "qdrant_client": version("qdrant-client"),
                         "torch": torch.__version__, "reranker_device": "cuda" if torch.cuda.is_available() else "cpu", "torch_threads": torch.get_num_threads()},
              "dataset_hashes": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in ("retrieval_questions.jsonl", "expected_citations.jsonl", "retrieval_corpus.json")},
              "notes": ["Small synthetic diagnostic set, not statistical evidence of general superiority.",
                        "One OCR case is explicitly simulated at confidence 0.54; real PaddleOCR validated separately.",
                        "No relevance threshold: missing-evidence queries may return unrelated nearest neighbors.",
                        "Metrics at source/page level; repeated source/page hits count once. Precision denominator is requested K."], "strategies": {}}
    for strategy in ("dense", "sparse", "hybrid", "hybrid_rerank"):
        rows = []
        # Record the first request per strategy; earlier strategies may warm shared models.
        with SessionLocal() as session:
            cold = retrieve(RetrieveRequest(query=questions[0]["query"], strategy=strategy, filters=RetrievalFilters(access_scope=SCOPE, synthetic=True)), session)
        for question in questions:
            with SessionLocal() as session:
                response = retrieve(RetrieveRequest(query=question["query"], top_k=question["top_k"], strategy=strategy,
                                                    filters=RetrievalFilters(access_scope=SCOPE, synthetic=True)), session)
            relevance = {f"{c['source_filename']}:{c['page']}": c["grade"] for c in expected[question["question_id"]]}
            source_ids = [f"{r.citation.source_filename}:{r.citation.page_start}" for r in response.results]
            # Validate every emitted quote/locator against the actual persisted point.
            qdrant = get_qdrant()
            stored = {str(p.id): p.payload for p in qdrant.client.retrieve(qdrant.collection, ids=[str(r.chunk_id) for r in response.results], with_payload=True)} if response.results else {}
            for result in response.results:
                payload = stored[str(result.chunk_id)]
                assert result.citation.quote == payload["content"]
                assert result.citation.source_sha256 == payload["source_sha256"]
                assert result.citation.page_start == payload["page_start"]
                assert result.citation.ocr_confidence == payload.get("ocr_confidence")
            rows.append({"question_id": question["question_id"], "category": question["category"], "query": question["query"],
                         "metrics": metrics(source_ids, relevance, question["top_k"]), "response": response.model_dump(mode="json")})
        report["strategies"][strategy] = {"metrics": aggregate([r["metrics"] for r in rows]),
                                         "first_request_timings_ms": cold.timings_ms,
                                         "mean_timings_ms": {name: mean(r["response"]["timings_ms"].get(name, 0) for r in rows) for name in cold.timings_ms},
                                         "by_category": {cat: aggregate([r["metrics"] for r in rows if r["category"] == cat]) for cat in sorted({r["category"] for r in rows})}, "queries": rows}
        print(strategy, report["strategies"][strategy]["metrics"], flush=True)
    manifest = settings.model_root / "bge-reranker-base/download_manifest.json"
    report["reranker_artifact"] = json.loads(manifest.read_text()) if manifest.exists() else None
    output = root / "results/retrieval_phase3b2.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Result:", output)


if __name__ == "__main__":
    main()
