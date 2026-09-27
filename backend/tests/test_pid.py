"""P&ID validation/preprocessing tests without downloading or running OCR models."""
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import unittest

import cv2
import numpy as np
import pymupdf
from PIL import Image
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.core.config import settings
from app.schemas.pid import PIDPage, PIDManifest, PIDProcessRequest, PIDProcessResponse, PreprocessOptions, OCRDetection
from app.services.pid_images import read_pid_source, load_image, preprocess, render_pages, check_pixels, save_png
from app.services.pid_identifiers import normalize_identifier, classify_text
from app.services.paddle_ocr import normalize_result, PaddleOCRService
from app.services.pid_regions import group_regions
from app.services.pid_processing import check_duplicate, request_metadata, process_pid
from app.services.ingestion import IngestionConflict
from app.db.models.document import Document
from app.db.models.document_version import DocumentVersion
from app.db.session import get_db
from app.main import app


class MemorySession:
    """Only persistence is replaced; exercise the real processing/API code."""
    def __init__(self):
        self.documents = {}
        self.versions = {}

    def scalar(self, statement, params=None):
        if params is not None:
            return True  # PostgreSQL lock is exercised separately by live validation.
        checksum = statement.compile().params["source_sha256_1"]
        return next((v for v in self.versions.values() if v.source_sha256 == checksum), None)

    def get(self, model, identifier):
        return self.documents.get(identifier)

    def add(self, record):
        (self.documents if isinstance(record, Document) else self.versions)[record.id] = record

    def flush(self):
        pass

    def commit(self):
        pass


def page_info(**updates):
    return PIDPage(page=1, width=200, height=100,
                   source_image_uri="processed/pids/page_images/test/rendered.png",
                   processed_image_uri="processed/pids/page_images/test/processed.png",
                   render_dpi=None, original_resolution={}, preprocessing=PreprocessOptions(),
                   processed_to_rendered=np.eye(3).tolist()).model_copy(update=updates)


def result(text="P-101A", bbox=(10, 10, 80, 35)):
    x1, y1, x2, y2 = bbox
    return {"rec_texts": [text], "rec_scores": [0.96],
            "rec_polys": [[[x1, y1], [x2, y1], [x2, y2], [x1, y2]]]}


class PIDTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.patch = patch.object(settings, "data_root", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.source = self.root / "raw/pids/source"
        self.source.mkdir(parents=True)

    def png(self):
        image = Image.new("RGB", (200, 100), "white")
        output = BytesIO()
        image.save(output, format="PNG", dpi=(300, 300))
        return output.getvalue()

    def test_path_and_format_restrictions(self):
        path = self.source / "test.png"
        source = self.png()
        path.write_bytes(source)
        self.assertEqual(read_pid_source("test.png"), (path.resolve(), source))
        for name in ("../../.env", "../test.png", str(path), "C:\\Windows\\file.png", "https://host/test.png", "file.gif", "test.png:stream"):
            with self.assertRaises(ValueError, msg=name):
                read_pid_source(name)
        with patch("app.services.pid_images.MAX_BYTES", 2):
            with self.assertRaises(ValueError):
                read_pid_source("test.png")

    def test_image_validation_and_resolution(self):
        pixels, metadata = load_image(self.png(), ".png")
        self.assertEqual(pixels.shape, (100, 200, 3))
        self.assertAlmostEqual(metadata["dpi"][0], 300, delta=1)
        for data, suffix in ((b"bad", ".png"), (self.png(), ".jpeg")):
            with self.assertRaises(ValueError):
                load_image(data, suffix)
        with self.assertRaises(ValueError):
            check_pixels(10000, 10000)

    def test_jpeg_exif_orientation(self):
        image = Image.new("RGB", (200, 100), "white")
        exif = image.getexif()
        exif[274] = 6
        output = BytesIO()
        image.save(output, format="JPEG", exif=exif)
        pixels, metadata = load_image(output.getvalue(), ".jpg")
        self.assertEqual(metadata["exif_orientation"], 6)
        self.assertEqual((metadata["width"], metadata["height"]), (200, 100))
        self.assertEqual(pixels.shape, (200, 100, 3))

    def test_preprocess_preserves_input_and_transforms(self):
        image = np.full((100, 200, 3), 240, dtype=np.uint8)
        cv2.putText(image, "P-101A", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        original = image.copy()
        for rotation in (0, 90, 180, 270):
            output, transform = preprocess(image, PreprocessOptions(rotation_degrees=rotation, denoise=True, adaptive_threshold=True))
            self.assertEqual(output.ndim, 2)
            self.assertEqual(transform.shape, (3, 3))
            self.assertTrue(set(np.unique(output)) <= {0, 255})
        np.testing.assert_array_equal(image, original)

    def test_render_artifacts_and_pdf_dpi(self):
        source = self.png()
        pages = list(render_pages(source, ".png", uuid4(), 300, PreprocessOptions()))
        for uri in (pages[0].source_image_uri, pages[0].processed_image_uri):
            self.assertTrue((self.root / uri).is_file())
        self.assertIsNone(pages[0].render_dpi)
        with pymupdf.open() as pdf:
            pdf.new_page(width=72, height=72)
            data = pdf.tobytes()
        rendered = list(render_pages(data, ".pdf", uuid4(), 300, PreprocessOptions()))
        self.assertEqual((rendered[0].width, rendered[0].height), (300, 300))
        self.assertEqual(rendered[0].render_dpi, 300)
        with self.assertRaises(ValueError):
            list(render_pages(b"not pdf", ".pdf", uuid4(), 300, PreprocessOptions()))
        with self.assertRaises(ValidationError):
            PIDProcessRequest(source_path="test.pdf", title="Test", render_dpi=200)

    def test_ocr_normalization_and_bbox(self):
        detection = normalize_result(result("P – 101 A"), page_info())[0]
        self.assertEqual(detection.text, "P – 101 A")
        self.assertEqual(detection.normalized_text, "P-101A")
        self.assertEqual(detection.bbox, (10, 10, 80, 35))
        self.assertEqual(detection.confidence, 0.96)
        self.assertEqual(detection.page, 1)
        self.assertEqual(detection.category, "equipment_tag")
        for update in ({"confidence": 2}, {"bbox": (-1, 0, 10, 10)}, {"bbox": (1, 1, 1, 2)}, {"confidence": float("nan")}):
            with self.assertRaises(ValidationError):
                OCRDetection.model_validate(detection.model_dump() | update)
        with self.assertRaises(ValueError):
            normalize_result(result(bbox=(10, 10, 300, 40)), page_info())
        with self.assertRaises(ValueError):
            normalize_result({"rec_texts": ["text"]}, page_info())

    def test_rotation_back_projection(self):
        _, inverse = preprocess(np.zeros((100, 200, 3), dtype=np.uint8), PreprocessOptions(rotation_degrees=90))
        detection = normalize_result(result(bbox=(59, 10, 79, 30)), page_info(processed_to_rendered=inverse.tolist()))[0]
        np.testing.assert_allclose(detection.bbox, (10, 20, 30, 40))

    def test_identifier_categories(self):
        cases = {"P-101A": "equipment_tag", "V-101": "equipment_tag", "E-101": "equipment_tag",
                 "P-101B": "equipment_tag", "C-101": "equipment_tag", "XV-101D": "valve_tag", "NRV-101": "valve_tag",
                 "TT-101": "instrument_tag", "PT-101": "instrument_tag", "FT-101": "instrument_tag",
                 "FV-101": "valve_tag", '6"-CW-1001-A': "line_number", "80 °C": "temperature_value",
                 "6.2 barg": "pressure_value", "REV: A": "revision", "P&ID TEST DRAWING": "drawing_title",
                 "unrecognized prose": "other_text"}
        for value, category in cases.items():
            self.assertEqual(classify_text(value)[1], category, value)
        self.assertEqual(normalize_identifier(" P − 101 B "), "P-101B")
        self.assertEqual(normalize_identifier("P-1O1A"), "P-1O1A")
        self.assertEqual(classify_text("P-1O1A")[1], "other_text")
        self.assertIn("FV-101", classify_text("FV-101")[2]["instrument_tags"])

    def test_regions_and_page_isolation(self):
        first = normalize_result(result(), page_info())[0]
        nearby = normalize_result(result("V-101", (85, 10, 150, 35)), page_info())[0]
        other_page = normalize_result(result("TT-101"), page_info(page=2))[0]
        version = uuid4()
        regions = group_regions([first, nearby, other_page], version)
        self.assertEqual(len(regions), 2)
        self.assertEqual(regions[0].region_type, "equipment_label")
        self.assertEqual(regions[0].identified_tags["equipment_tags"], ["P-101A", "V-101"])
        self.assertEqual(regions, group_regions([first, nearby, other_page], version))
        self.assertNotIn("connectivity", regions[0].model_dump())

    def test_duplicate_processing_contract(self):
        request = PIDProcessRequest(source_path="test.png", title="Test")
        version = SimpleNamespace(document_id=uuid4(), status="pid_processed",
                                  ingestion_metadata={"kind": "pid", "request": request_metadata(request)})
        self.assertTrue(check_duplicate(version, request))
        version.status = "pid_failed"
        self.assertFalse(check_duplicate(version, request))
        with self.assertRaises(IngestionConflict):
            check_duplicate(version, request.model_copy(update={"title": "Different"}))
        with self.assertRaises(IngestionConflict):
            check_duplicate(version, request.model_copy(update={"document_id": uuid4()}))
        version.ingestion_metadata["kind"] = "sop"
        with self.assertRaises(IngestionConflict):
            check_duplicate(version, request)

    def test_manifest_validation(self):
        manifest = PIDManifest(
            document_id=uuid4(), document_version_id=uuid4(), source_filename="test.png",
            source_uri="raw/pids/source/test.png", source_sha256="a" * 64, page_count=1,
            render_dpi=None, ocr_model=["PP-OCRv5_server_det", "PP-OCRv5_server_rec"],
            processed_at=datetime.now(timezone.utc), synthetic=True, warnings=[], pages=[page_info()],
            ocr_json_uri="processed/pids/ocr_json/test.json", region_json_uri="processed/pids/regions/test.json",
            ocr_detections=1, regions=1, equipment_tags=["P-101A"], instrument_tags=[],
        )
        self.assertEqual(PIDManifest.model_validate_json(manifest.model_dump_json()), manifest)
        for change in ({"source_sha256": "bad"}, {"page_count": 2}):
            with self.assertRaises(ValidationError):
                PIDManifest.model_validate(manifest.model_dump() | change)

    def test_model_reuse_and_page_processing(self):
        calls = []
        predictor = SimpleNamespace(predict=lambda **kwargs: calls.append(kwargs) or [result()])
        service = PaddleOCRService()
        service._model = predictor
        pages = list(service.recognize_pages([page_info(), page_info(page=2)]))
        self.assertEqual(len(calls), 2)
        self.assertEqual(pages[1][0].page, 2)
        self.assertIs(service._model, predictor)

    def test_uncertain_ocr_is_never_verified(self):
        raw = result("XV-1010") | {"rec_scores": [0.54]}
        detection = normalize_result(raw, page_info())[0]
        self.assertEqual(detection.text, "XV-1010")
        self.assertEqual(detection.normalized_text, "XV-1010")
        self.assertEqual(detection.status, "ambiguous")
        self.assertTrue(detection.ocr_derived)
        self.assertEqual(normalize_result(result(), page_info())[0].status, "unverified")
        with self.assertRaises(ValidationError):
            OCRDetection.model_validate(detection.model_dump() | {"status": "verified"})

    def test_images_are_not_overwritten_on_retry(self):
        version = uuid4()
        page = list(render_pages(self.png(), ".png", version, 300, PreprocessOptions()))[0]
        paths = [self.root / uri for uri in (page.source_image_uri, page.processed_image_uri)]
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
        list(render_pages(self.png(), ".png", version, 300, PreprocessOptions()))
        self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths])
        with self.assertRaises(ValueError):
            save_png(paths[0], np.zeros((100, 200, 3), dtype=np.uint8))
        self.assertEqual(paths[0].read_bytes(), before[0][0])

    def test_api_processing_duplicate_and_sha256(self):
        path = self.source / "test.png"
        path.write_bytes(self.png())
        checksum = sha256(path.read_bytes()).hexdigest()
        source_mtime = path.stat().st_mtime_ns
        session = MemorySession()
        calls = []

        def recognize(pages):
            for page in pages:
                calls.append(page)
                yield normalize_result(result(), page)

        app.dependency_overrides[get_db] = lambda: session
        self.addCleanup(app.dependency_overrides.pop, get_db)
        from app.api.deps import get_optional_current_user
        from app.db.models import User
        actor = User(id=uuid4(), username="phase11-admin", role="admin")
        app.dependency_overrides[get_optional_current_user] = lambda: actor
        self.addCleanup(app.dependency_overrides.pop, get_optional_current_user)
        with patch("app.services.pid_processing.get_paddle_ocr", return_value=SimpleNamespace(recognize_pages=recognize)), TestClient(app) as client:
            body = {"source_path": "test.png", "title": "Synthetic test", "synthetic": True}
            response = client.post("/documents/pid/process", json=body)
            self.assertEqual(response.status_code, 200, response.text)
            processed = PIDProcessResponse.model_validate(response.json())
            self.assertEqual(processed.status, "processed")
            self.assertEqual(processed.source_sha256, checksum)
            manifest = PIDManifest.model_validate_json((self.root / processed.manifest_uri).read_text(encoding="utf-8"))
            self.assertEqual(manifest.document_version_id, processed.document_version_id)
            self.assertEqual(manifest.ocr_detections, 1)
            duplicate = client.post("/documents/pid/process", json=body)
            self.assertEqual(duplicate.status_code, 200, duplicate.text)
            self.assertEqual(duplicate.json()["status"], "duplicate")
            self.assertEqual(duplicate.json()["document_version_id"], str(processed.document_version_id))
            self.assertEqual(len(calls), 1)
            self.assertEqual((len(session.documents), len(session.versions)), (1, 1))
            self.assertEqual(client.post("/documents/pid/process", json=body | {"title": "Conflict"}).status_code, 409)
            self.assertEqual(client.post("/documents/pid/process", json=body | {"source_path": "../test.png"}).status_code, 422)
            self.assertEqual(client.post("/documents/pid/process", json=body | {"render_dpi": 401}).status_code, 422)
        self.assertEqual(sha256(path.read_bytes()).hexdigest(), checksum)
        self.assertEqual(path.stat().st_mtime_ns, source_mtime)

    def test_failed_ocr_retry_reuses_version_and_rendered_images(self):
        (self.source / "test.png").write_bytes(self.png())
        session = MemorySession()
        request = PIDProcessRequest(source_path="test.png", title="Retry")

        def failed(pages):
            raise RuntimeError("Synthetic OCR failure")

        with self.assertRaises(RuntimeError):
            process_pid(request, session, SimpleNamespace(recognize_pages=failed))
        version = next(iter(session.versions.values()))
        self.assertIsInstance(version, DocumentVersion)
        self.assertEqual(version.status, "pid_failed")
        image_paths = list((self.root / "processed/pids/page_images").rglob("*.png"))
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in image_paths]
        ocr = SimpleNamespace(recognize_pages=lambda pages: iter([normalize_result(result(), pages[0])]))
        response = process_pid(request, session, ocr)
        self.assertEqual(response.document_version_id, version.id)
        self.assertEqual(response.status, "processed")
        self.assertEqual(len(session.versions), 1)
        self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in image_paths])

    def test_symlink_escape_is_rejected(self):
        outside = self.root / "outside.png"
        outside.write_bytes(self.png())
        link = self.source / "link.png"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("Host does not permit creating symlinks")
        with self.assertRaises(ValueError):
            read_pid_source("link.png")

    def test_new_source_revision_preserves_existing_evidence(self):
        first_source = self.source / "first.png"
        first_source.write_bytes(self.png())
        session = MemorySession()
        ocr = SimpleNamespace(recognize_pages=lambda pages: iter([normalize_result(result(), pages[0])]))
        first = process_pid(PIDProcessRequest(source_path=first_source.name, title="Revision test"), session, ocr)
        old_manifest = (self.root / first.manifest_uri).read_bytes()
        second_source = self.source / "second.png"
        image = Image.new("RGB", (200, 100), "gray")
        image.save(second_source)
        second = process_pid(PIDProcessRequest(source_path=second_source.name, title="Revision test",
                                               document_id=first.document_id), session, ocr)
        self.assertEqual(second.document_id, first.document_id)
        self.assertNotEqual(second.document_version_id, first.document_version_id)
        self.assertNotEqual(second.source_sha256, first.source_sha256)
        self.assertEqual((len(session.documents), len(session.versions)), (1, 2))
        self.assertEqual((self.root / first.manifest_uri).read_bytes(), old_manifest)
        self.assertEqual(sha256(first_source.read_bytes()).hexdigest(), first.source_sha256)
