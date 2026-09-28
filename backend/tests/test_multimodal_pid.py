"""B1 deterministic contracts; all images synthetic, all model HTTP mocked."""
import json
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
from PIL import Image
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.pid import VisualCandidate, VisionEvidence, PIDProcessRequest, PIDManifest, OCRRegion
from app.services.local_vision import LocalVisionAdapter
from app.services.pid_fusion import fuse, region_fusion, registry_evidence
from app.services.pid_processing import process_pid
from app.services.pid_evidence import load_pid_evidence
from app.services.pid_indexing import region_chunks
from app.services.paddle_ocr import normalize_result
from app.services.pid_regions import group_regions
from app.services.model_routing import select_model, RiskSignals
from app.services.evidence_sufficiency import assess
from app.services.visual_intelligence import observations
from app.agents.evidence import pid_region_evidence
from app.agents.pid_evidence import drawing_tags
from app.services.model_gateway.errors import ModelConfigurationError
from test_pid import page_info, result, MemorySession


def visual(tag="P-101A", **kwargs):
    return VisualCandidate(bbox=(10, 10, 80, 35), region_type="label", tag=tag,
                           confidence=.99, uncertainty="unverified_visual_observation", **kwargs)


def detection(confidence=.96):
    return normalize_result(result() | {"rec_scores": [confidence]}, page_info())[0]


def ref(visuals=True):
    item = detection()
    value = pid_region_evidence(region_id=uuid4(), document_id=uuid4(), document_version_id=uuid4(),
        source_filename="synthetic.png", source_sha256="a"*64, page=1, bbox=item.bbox,
        confidence=item.confidence, ocr_status="unverified", combined_text=item.text,
        source_image_uri=item.source_image, revision="R1", text_items=[item])
    value.visual_candidates = [visual()] if visuals else []
    value.visual_model = "qwen3.5:9b" if visuals else None
    value.fusion = [fuse(item, value.visual_candidates)]
    return value


class FusionTests(unittest.TestCase):
    def test_a_high_ocr_authoritative_registry(self):
        value = fuse(detection(), [visual()], {"status":"verified", "tag":"P-101A", "knowledge_id":"reviewed"})
        self.assertEqual(value.registry_status, "VERIFIED")
        self.assertIn("HUMAN_VERIFIED", value.evidence_origin)

    def test_b_low_ocr_stays_candidate(self):
        value = fuse(detection(.3), [visual()], {"status":"verified", "tag":"P-101A"})
        self.assertEqual(value.registry_status, "CANDIDATE")
        self.assertTrue(value.review_required)

    def test_c_visual_without_registry(self):
        self.assertEqual(fuse(visuals=[visual()]).registry_status, "UNVERIFIED")

    def test_d_ocr_visual_disagreement(self):
        self.assertEqual(fuse(detection(), [visual("P-102A")]).registry_status, "CONFLICTING")

    def test_e_registry_disagreement(self):
        self.assertEqual(fuse(detection(), registry={"status":"verified", "tag":"P-102A"}).registry_status, "CONFLICTING")
        self.assertEqual(fuse(detection(), registry={"status":"missing", "tag":"P-101A"}).registry_status, "CONFLICTING")

    def test_inventory_presence_is_not_authority(self):
        session = MagicMock()
        session.scalar.return_value = SimpleNamespace(id=uuid4())
        session.scalars.return_value.all.return_value = []
        self.assertEqual(registry_evidence(session, "P-101A")["status"], "matched")
        self.assertEqual(fuse(detection(), registry=registry_evidence(session, "P-101A")).registry_status, "CANDIDATE")

    def test_registry_requires_current_human_approval(self):
        session = MagicMock()
        session.scalar.return_value = SimpleNamespace(id=uuid4())
        record = SimpleNamespace(id=uuid4(), approval_revision_id=uuid4(), source_snapshot=[{"revision":"R2"}])
        session.scalars.return_value.all.return_value = [record]
        with patch("app.services.verified_knowledge.refresh", return_value=True) as refresh:
            value = registry_evidence(session, "P-101A")
            self.assertEqual(value["status"], "verified")
            self.assertEqual(value["knowledge_id"], str(record.id))
            refresh.assert_called_once_with(session, record)
        with patch("app.services.verified_knowledge.refresh", return_value=False):
            self.assertEqual(registry_evidence(session, "P-101A")["status"], "matched")

    def test_g_h_i_deterministic_operational_refusals(self):
        for query in ("Is the valve closed?", "Does image geometry prove isolation?", "OCR topology upstream?",
                      "LOTO state?", "startup readiness?", "shutdown readiness?", "safe to operate?", "permit state?"):
            with self.subTest(query=query):
                answer = drawing_tags(query, [ref()])
                self.assertEqual(answer["agent_result"]["schema"], "S5")
                self.assertTrue(answer["human_approval_required"])

    def test_j_provenance(self):
        source = ref()
        observation = observations([source])[0]
        self.assertEqual(observation["provenance"]["source_hash"], source.source_sha256)
        self.assertEqual(observation["provenance"]["revision"], "R1")
        self.assertEqual(observation["visual_candidates"][0]["bbox"], [10.,10.,80.,35.])
        self.assertEqual(observation["fusion"][0]["ocr_confidence"], .96)
        self.assertEqual(observation["fusion"][0]["visual_confidence"], .99)

    def test_m_sufficiency_is_not_visual_confidence(self):
        value = ref()
        measured = assess("P&ID evidence", [value], citations=[{"evidence_id":value.evidence_id,"locator":value.locator,"claim":"Candidate label"}])
        self.assertEqual(measured["state"], "PARTIAL")

    def test_n_ambiguous_equipment_requires_review(self):
        value = fuse(visuals=[visual(), visual("P-102A")])
        self.assertTrue(value.review_required)
        self.assertEqual(value.registry_status, "CONFLICTING")
        self.assertIsNone(value.visual_confidence)

    def test_visual_uncertainty_requires_review_despite_registry_match(self):
        candidate = visual().model_copy(update={"uncertainty":"ambiguous_label"})
        value = fuse(detection(), [candidate], {"status":"verified", "tag":"P-101A"})
        self.assertTrue(value.review_required)
        self.assertNotEqual(value.registry_status, "VERIFIED")

    def test_p_legacy_region_defaults(self):
        region = group_regions([detection()], uuid4())[0]
        data = region.model_dump(exclude={"visual_candidates", "visual_model"})
        self.assertEqual(OCRRegion.model_validate(data).visual_candidates, [])
        self.assertEqual(drawing_tags("Show P&ID labels", [ref(False)])["agent_result"]["schema"], "S3")

    def test_q_deep_routing(self):
        for query, signals in (("classify visual region", RiskSignals()), ("helper", RiskSignals(ocr_confidence=.2)),
                               ("helper", RiskSignals(conflicting_evidence=True)), ("P&ID isolation", RiskSignals()),
                               ("helper", RiskSignals(pid_uncertainty=True)), ("helper", RiskSignals(critical_tag_verification=True)),
                               ("upstream topology", RiskSignals()), ("is it safe to start", RiskSignals())):
            self.assertEqual(select_model(query, task="classification", signals=signals)["model_selected"], "qwen3.5:9b")
        self.assertEqual(drawing_tags("Show P&ID around P-101A", [ref()])["agent_result"]["model_routing"]["model_selected"], "qwen3.5:9b")

    def test_model_cannot_emit_operational_claim_or_authority(self):
        data = visual().model_dump()
        for updates in ({"tag":"P-101A is closed"}, {"registry_status":"VERIFIED"}, {"uncertainty":"Valve is closed"}, {"confidence":float("nan")}):
            with self.assertRaises(ValidationError): VisualCandidate.model_validate(data | updates)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.page = page_info()
        path = self.root / self.page.source_image_uri
        path.parent.mkdir(parents=True)
        Image.new("RGB", (200,100), "white").save(path)
        self.config = settings.model_copy(update={"data_root":self.root, "pid_vision_enabled":True,
            "model_runtime":"ollama", "model_base_url":"http://127.0.0.1:11434", "pid_vision_model":"qwen3.5:9b"})
        self.requests = []

    def handler(self, request):
        self.requests.append(request)
        if request.url.path == "/api/tags": return httpx.Response(200, json={"models":[{"name":"qwen3.5:9b"}]})
        if request.url.path == "/api/show": return httpx.Response(200, json={"capabilities":["vision"]})
        return httpx.Response(200, json={"done":True, "done_reason":"stop", "message":{"content":json.dumps({"candidates":[visual().model_dump()]})}})

    def test_local_success_and_protocol(self):
        adapter = LocalVisionAdapter(self.config, httpx.MockTransport(self.handler))
        result = adapter.analyze(self.page)
        self.assertEqual(result.status, "available")
        self.assertEqual(result.call_count, 1)
        payload = json.loads(self.requests[-1].content)
        self.assertEqual(payload["model"], "qwen3.5:9b")
        self.assertTrue(payload["messages"][0]["images"])
        self.assertNotIn("/api/pull", [r.url.path for r in self.requests])

    def test_k_unavailable_fallback(self):
        adapter = LocalVisionAdapter(self.config, httpx.MockTransport(lambda r: httpx.Response(503)))
        value = adapter.analyze(self.page)
        self.assertEqual(value.status, "unavailable")
        self.assertEqual(value.candidates, [])
        self.assertEqual(value.call_count, 0)

    def test_l_hosted_and_cloud_rejected(self):
        for url in ("https://api.openai.com", "http://8.8.8.8", "http://user:secret@localhost"):
            with self.assertRaises(ModelConfigurationError):
                LocalVisionAdapter(self.config.model_copy(update={"model_base_url":url,"model_allowed_hosts":"api.openai.com,8.8.8.8,localhost"}))
        with self.assertRaises(ModelConfigurationError):
            LocalVisionAdapter(self.config.model_copy(update={"pid_vision_model":"model:cloud"}))

    def test_o_malformed_image_safe_failure(self):
        (self.root / self.page.source_image_uri).write_bytes(b"malformed")
        value = LocalVisionAdapter(self.config, httpx.MockTransport(self.handler)).analyze(self.page)
        self.assertEqual(value.status, "unavailable")
        self.assertEqual(value.call_count, 0)

    def test_redirect_not_followed(self):
        value = LocalVisionAdapter(self.config, httpx.MockTransport(lambda r: httpx.Response(302, headers={"Location":"https://api.openai.com"}))).analyze(self.page)
        self.assertEqual(value.status, "unavailable")

    def test_timeout_and_missing_model(self):
        def timeout(request): raise httpx.ReadTimeout("synthetic timeout")
        self.assertEqual(LocalVisionAdapter(self.config, httpx.MockTransport(timeout)).health(), (False,"runtime_unavailable"))
        adapter = LocalVisionAdapter(self.config, httpx.MockTransport(lambda r: httpx.Response(200,json={"models":[]})))
        self.assertEqual(adapter.health(), (False,"model_not_installed"))

    def test_r_persisted_processing_not_repeated(self):
        source = self.root / "raw/pids/source/test.png"
        source.parent.mkdir(parents=True)
        Image.new("RGB", (200,100), "white").save(source)
        session = MemorySession()
        ocr = MagicMock()
        ocr.recognize_pages.side_effect = lambda pages: iter([normalize_result(result(), pages[0])])
        vision = MagicMock()
        vision.analyze.side_effect = lambda page: VisionEvidence(status="available", model="mock-local", page=page.page,
            source_image_uri=page.source_image_uri, candidates=[visual()], call_count=1)
        request = PIDProcessRequest(source_path="test.png", title="Synthetic", revision="R1")
        with patch.object(settings, "data_root", self.root):
            first = process_pid(request, session, ocr, vision)
            second = process_pid(request, session, ocr, vision)
            self.assertEqual(second.status, "duplicate")
            self.assertEqual(vision.analyze.call_count, 1)
            self.assertEqual(ocr.recognize_pages.call_count, 1)
            manifest = PIDManifest.model_validate_json((self.root / first.manifest_uri).read_text())
            self.assertEqual(manifest.vision[0].candidates[0].tag, "P-101A")
            self.assertEqual(manifest.operational_metadata["visual_model_call_count"], 1)

    def test_interrupted_processing_reuses_completed_vision(self):
        source = self.root / "raw/pids/source/test.png"
        source.parent.mkdir(parents=True)
        Image.new("RGB", (200,100), "white").save(source)
        ocr = MagicMock()
        ocr.recognize_pages.side_effect = lambda pages: iter([normalize_result(result(), pages[0])])
        vision = MagicMock(model="mock-local")
        vision.analyze.side_effect = lambda page: VisionEvidence(status="available", model="mock-local", page=page.page,
            source_image_uri=page.source_image_uri, candidates=[visual()], call_count=1)
        request = PIDProcessRequest(source_path="test.png", title="Synthetic", revision="R1")
        with patch.object(settings, "data_root", self.root):
            with patch("app.services.pid_processing.group_regions", side_effect=RuntimeError("interrupted")):
                with self.assertRaises(RuntimeError):
                    process_pid(request, MemorySession(), ocr, vision)
            # A fresh session models a hard kill: the version row rolled back, so ids differ.
            done = process_pid(request, MemorySession(), ocr, vision)
            self.assertEqual(vision.analyze.call_count, 1)
            manifest = PIDManifest.model_validate_json((self.root / done.manifest_uri).read_text())
            self.assertEqual(manifest.vision[0].candidates[0].tag, "P-101A")
            self.assertEqual(manifest.vision[0].source_image_uri, manifest.pages[0].source_image_uri)
            self.assertEqual(manifest.operational_metadata["vision_pages_reused"], 1)
            # Unavailable results are never persisted, so vision is retried once it recovers.
            other = MagicMock(model="other-local")
            other.analyze.return_value = VisionEvidence(model="other-local", page=1, source_image_uri="x", fallback_reason="disabled")
            process_pid(request, MemorySession(), ocr, other)
            process_pid(request, MemorySession(), ocr, other)
            self.assertEqual(other.analyze.call_count, 2)


class SourceTests(unittest.TestCase):
    def setUp(self):
        from test_phase6 import Phase6Tests
        self.fixture = Phase6Tests()
        self.fixture.setUp()
        from app.db.models import VerifiedKnowledge
        VerifiedKnowledge.__table__.create(self.fixture.engine)
        self.fixture.document_version.created_at = datetime.now(timezone.utc)
        self.fixture.session.commit()
        self.addCleanup(self.fixture.doCleanups)

    def test_f_new_revision_invalidates_derived_evidence(self):
        from app.db.models import DocumentVersion
        f = self.fixture
        self.assertTrue(f.refs())
        version = DocumentVersion(id=uuid4(), document_id=f.document.id, source_sha256="b"*64,
            status="pid_processing", chunk_count=0, warnings=[], ingestion_metadata={"kind":"pid"},
            created_at=f.document_version.created_at + timedelta(seconds=1))
        f.session.add(version)
        f.session.commit()
        with self.assertRaisesRegex(ValueError, "stale"): f.refs()

    def test_visual_load_and_index_preserve_existing_contract(self):
        f = self.fixture
        f.region.visual_candidates = [visual()]
        f.region.visual_model = "mock-local"
        f.write_regions()
        refs = f.refs()
        self.assertEqual(refs[0].visual_candidates[0].tag, "P-101A")
        self.assertEqual(refs[0].fusion[0].registry_status, "CONFLICTING")
        from test_hybrid import TestTokenizer
        path = f.root / f"processed/pids/manifests/{f.document_version.id}.json"
        manifest = PIDManifest.model_validate_json(path.read_text())
        chunks = region_chunks(manifest, [f.region], {"title":"Drawing", "access_scope":"internal"}, TestTokenizer())
        self.assertIn("Unverified visual candidate label: P-101A", chunks[0].content)
        self.assertTrue(chunks[0].ocr_derived)
        self.assertEqual(chunks[0].region_id, f.region.region_id)

    def test_legacy_artifact_keeps_original_integrity_hash(self):
        from app.services.canonicalization import canonical_hash
        f = self.fixture
        artifact = json.loads(f.region_path.read_text())
        region = artifact["regions"][0]
        region.pop("visual_candidates")
        region.pop("visual_model")
        f.region_path.write_text(json.dumps(artifact))
        reference = f.refs()[0]
        self.assertEqual(reference.ocr_region_hash, canonical_hash(region))
        self.assertEqual(reference.fusion, [])

    def test_visual_tampering_invalidates_integrity(self):
        from app.services.evidence_integrity import _pid_region_content
        f = self.fixture
        f.region.visual_candidates = [visual()]
        f.write_regions()
        before = _pid_region_content(f.refs()[0].model_dump(mode="json"))
        f.region.visual_candidates = [visual("P-102A")]
        f.write_regions()
        after = _pid_region_content(f.refs()[0].model_dump(mode="json"))
        self.assertNotEqual(before, after)

    def test_visual_only_region_retrievable(self):
        f = self.fixture
        f.region.text_items = []
        f.region.combined_text = ""
        f.region.visual_candidates = [visual()]
        f.region.visual_model = "mock-local"
        f.write_regions()
        self.assertEqual(len(f.refs()), 1)
        from test_hybrid import TestTokenizer
        manifest = PIDManifest.model_validate_json((f.root / f"processed/pids/manifests/{f.document_version.id}.json").read_text())
        chunks = region_chunks(manifest, [f.region], {"title":"Drawing", "access_scope":"internal"}, TestTokenizer())
        self.assertEqual(len(chunks), 1)
        self.assertIsNone(chunks[0].ocr_engine)
        self.assertEqual(drawing_tags("Show P&ID", f.refs())["agent_result"]["schema"], "S3")
