"""Real hybrid/reranker path using the latest real Phase 3B1 OCR fixture."""
import json
import hashlib
import math
from pathlib import Path
from fastapi.testclient import TestClient
from app.core.config import settings
from app.main import app
from app.services.qdrant_service import get_qdrant


def main():
    qdrant = get_qdrant()
    pid = json.loads((settings.data_root / "processed/pids/manifests/phase3b1_smoke_result.json").read_text())
    assert pid["fresh_ocr_run"]
    version = pid["response"]["document_version_id"]
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (settings.data_root / "raw").rglob("*") if p.is_file()}
    before = qdrant.client.count(qdrant.collection).count
    with TestClient(app) as client:
        indexed = client.post(f"/documents/pid/{version}/index")
        assert indexed.status_code == 200, indexed.text
        count = qdrant.client.count(qdrant.collection).count
        again = client.post(f"/documents/pid/{version}/index")
        assert again.status_code == 200 and again.json()["status"] == "duplicate", again.text
        assert qdrant.client.count(qdrant.collection).count == count
        responses = []
        for query in ("P-101A", "TT-101", "pump abnormal vibration procedure", "FV-101", "P&ID region containing P-101A"):
            for strategy in ("dense", "sparse", "hybrid", "hybrid_rerank"):
                response = client.post("/knowledge/retrieve", json={"query": query, "strategy": strategy, "top_k": 6,
                                                                    "filters": {"access_scope": "internal", "synthetic": True}})
                assert response.status_code == 200, response.text
                body = response.json()
                for result in body["results"]:
                    assert result["citation"]["quote"] == result["content"]
                    if result["citation"]["ocr_derived"]:
                        assert result["citation"]["region_id"] and result["citation"]["bounding_boxes"]
                responses.append(body)
        specific = client.post("/knowledge/retrieve", json={"query": "P-101A", "strategy": "hybrid_rerank", "filters": {"document_version_id": version}})
        assert specific.status_code == 200, specific.text
        assert any("P-101A" in r["content"] and r["citation"]["ocr_derived"] for r in specific.json()["results"])
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in hashes.items())
    backup = settings.qdrant_collection + "_dense_backup"
    originals, _ = qdrant.client.scroll(backup, limit=100, with_payload=True, with_vectors=True)
    current = {str(p.id): p for p in qdrant.client.retrieve(qdrant.collection, [p.id for p in originals], with_payload=True, with_vectors=True)}
    for original in originals:
        actual = current[str(original.id)]
        assert all(actual.payload[k] == v for k, v in original.payload.items() if k != "sparse_encoding")
        assert all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(original.vector["dense"], actual.vector["dense"]))
    backfill = qdrant.migrate_sparse()
    assert backfill["updated_points"] == 0
    report = {"pid_indexing": indexed.json(), "duplicate": again.json(), "points_before": before, "points_after": count,
              "original_points_preserved": len(originals), "original_source_files_unchanged": len(hashes),
              "backfill_repeat": backfill, "queries": responses, "pid_specific": specific.json()}
    output = settings.data_root / "evaluation/results/phase3b2_live.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("queries", "pid_specific")}, indent=2))


if __name__ == "__main__":
    main()
