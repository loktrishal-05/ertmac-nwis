"""Opt-in integration smoke test: real PostgreSQL, Qdrant, Docling, and BGE."""
import json
import math
from hashlib import sha256

import pymupdf
from fastapi.testclient import TestClient
from app.core.config import settings
from app.main import app
from app.services.embeddings import get_embeddings
from app.services.qdrant_service import get_qdrant


def main():
    path = settings.data_root / "raw/sops/source/phase3a_synthetic_numbered.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with pymupdf.open() as pdf:
            page = pdf.new_page()
            page.insert_text((50, 50), "1. Synthetic Pump Reference", fontsize=16)
            content = (
                "SYNTHETIC TEST DOCUMENT. NOT AN OPERATING PROCEDURE.\n\n"
                "P-101A is a fictional pump identifier used only to validate document retrieval. "
                "The applicable reference for P-101A is this synthetic pump reference. "
                "TT-101 and PT-101 are fictional instrument tags. No equipment should be operated "
                "using this test document.\n\n"
                "1. Locate the synthetic record for P-101A in the test index.\n"
                "2. Verify that the displayed evidence includes the original source filename.\n"
                "3. Confirm that the citation refers to page one of this generated PDF.\n"
                "4. Treat this record as software validation data and not refinery guidance.\n\n"
                "The synthetic revision is TEST-1. All names and tags in this reference are test "
                "fixtures created for local validation. This document contains no operational "
                "instructions, sensor measurements, maintenance advice, or real facility information."
            )
            assert page.insert_textbox(pymupdf.Rect(50, 85, 545, 750), content, fontsize=11) >= 0
            pdf.save(path)
    original_hash = sha256(path.read_bytes()).hexdigest()
    request = {
        "source_path": "sops/source/phase3a_synthetic_numbered.pdf",
        "title": "Synthetic Pump Reference", "document_type": "sop",
        "revision": "TEST-1", "synthetic": True, "facility_id": "test-only",
    }
    with TestClient(app) as client:
        result = client.post("/documents/ingest", json=request)
        assert result.status_code == 200, result.text
        ingestion = result.json()
        assert ingestion["status"] in ("indexed", "duplicate"), ingestion
        assert ingestion["chunk_count"] > 0
        qdrant = get_qdrant()
        count = qdrant.client.count(qdrant.collection).count
        repeated = client.post("/documents/ingest", json=request)
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["status"] == "duplicate"
        assert repeated.json()["document_version_id"] == ingestion["document_version_id"]
        assert qdrant.client.count(qdrant.collection).count == count
        conflict = client.post("/documents/ingest", json=request | {"title": "Conflicting metadata"})
        assert conflict.status_code == 409
        response = client.post("/knowledge/retrieve", json={
            "query": "What reference applies to pump P-101A?", "top_k": 6,
            "filters": {"synthetic": True, "document_version_id": ingestion["document_version_id"]},
        })
        assert response.status_code == 200, response.text
        evidence = response.json()
        assert evidence["results"], evidence
        for item in evidence["results"]:
            citation = item["citation"]
            assert citation["page_start"] == citation["page_end"] == 1
            assert citation["source_sha256"] == original_hash
            assert citation["source_filename"] == path.name
            assert citation["quote"] == item["content"]
            assert "P-101A" in item["content"]
            assert "1. Locate the synthetic record" in item["content"]
        embedding = get_embeddings().embed(["local embedding dimension check"])[0]
        assert len(embedding) == 768
        assert math.isclose(sum(v * v for v in embedding), 1.0, abs_tol=1e-5)
        assert original_hash == sha256(path.read_bytes()).hexdigest()
        report_path = settings.data_root / "processed/documents/extraction_reports" / (ingestion["document_version_id"] + ".json")
        extraction = json.loads(report_path.read_text(encoding="utf-8"))
        report = {"ingestion": ingestion, "extraction_method": extraction["extraction_method"],
                  "qdrant_point_count": count, "embedding_dimension": len(embedding),
                  "duplicate_verified": True, "raw_unchanged": True, "retrieval": evidence}
        output = settings.data_root / "indexes/ingestion_manifests/phase3a_smoke_result.json"
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
