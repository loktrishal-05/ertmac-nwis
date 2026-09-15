"""Opt-in real PP-OCRv5 + PostgreSQL validation; leaves a small synthetic fixture."""
from hashlib import sha256
from io import BytesIO
from time import perf_counter
from uuid import uuid4
import json
import cv2
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
from app.core.config import settings
from app.main import app
from app.schemas.pid import PIDManifest, OCRDetection
from app.services.qdrant_service import get_qdrant


def main():
    import sys
    if "--trace" in sys.argv:
        import faulthandler
        faulthandler.dump_traceback_later(60, repeat=True)
    fresh = "--fresh" in sys.argv
    run_id = uuid4().hex if fresh else None
    filename = f"phase3b1_synthetic_{run_id}.png" if fresh else "phase3b1_synthetic.png"
    source = settings.data_root / "raw/pids/source" / filename
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        image = np.full((850, 1200, 3), 255, dtype=np.uint8)
        cv2.putText(image, "P&ID SYNTHETIC TEST DRAWING", (55, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 0, 0), 2)
        for index, label in enumerate(("P-101A", "V-101", "E-101", "TT-101", "PT-101", "FV-101")):
            x, y = 100 + (index % 2) * 600, 180 + (index // 2) * 220
            cv2.putText(image, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)
            cv2.rectangle(image, (x + 60, y + 35), (x + 160, y + 100), (0, 0, 0), 2)
        cv2.putText(image, "REV: TEST1", (750, 800), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
        ok, encoded = cv2.imencode(".png", image)
        assert ok
        metadata = PngImagePlugin.PngInfo()
        if run_id:
            metadata.add_text("synthetic_validation_run", run_id)
        with Image.open(BytesIO(encoded.tobytes())) as fixture, source.open("xb") as stream:
            fixture.save(stream, format="PNG", pnginfo=metadata)
    original_hash = sha256(source.read_bytes()).hexdigest()
    qdrant = get_qdrant()
    before_count = qdrant.client.count(qdrant.collection).count
    body = {"source_path": source.name, "title": "Synthetic P&ID OCR Fixture", "revision": "TEST1", "synthetic": True}
    with TestClient(app) as client:
        started = perf_counter()
        response = client.post("/documents/pid/process", json=body)
        elapsed = perf_counter() - started
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] in ("processed", "duplicate"), result
        if fresh:
            assert result["status"] == "processed", "Fresh validation must run real OCR"
        expected = {"P-101A", "V-101", "E-101", "TT-101", "PT-101", "FV-101"}
        assert expected <= set(result["equipment_tags"] + result["instrument_tags"]), result
        manifest = PIDManifest.model_validate_json((settings.data_root / result["manifest_uri"]).read_text(encoding="utf-8"))
        ocr = json.loads((settings.data_root / manifest.ocr_json_uri).read_text(encoding="utf-8"))
        detections = [OCRDetection.model_validate(item) for item in ocr["detections"]]
        assert detections and all(item.page == 1 and item.polygon for item in detections)
        assert all(item.ocr_derived and item.status in ("unverified", "ambiguous") for item in detections)
        for page in manifest.pages:
            for uri in (page.source_image_uri, page.processed_image_uri):
                assert (settings.data_root / uri).is_file()
        assert (settings.data_root / manifest.region_json_uri).is_file()
        duplicate = client.post("/documents/pid/process", json=body)
        assert duplicate.status_code == 200, duplicate.text
        assert duplicate.json()["status"] == "duplicate"
        assert duplicate.json()["document_version_id"] == result["document_version_id"]
        conflict = client.post("/documents/pid/process", json=body | {"title": "Conflicting title"})
        assert conflict.status_code == 409
        assert sha256(source.read_bytes()).hexdigest() == original_hash == result["source_sha256"]
        assert qdrant.client.count(qdrant.collection).count == before_count
        report = {"response": result, "fresh_ocr_run": fresh, "processing_seconds": elapsed,
                  "duplicate_verified": True, "source_unchanged": True,
                  "qdrant_unchanged": True, "detections": [item.model_dump(mode="json") for item in detections]}
        output = settings.data_root / "processed/pids/manifests/phase3b1_smoke_result.json"
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    if "--trace" in sys.argv:
        faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    main()
