"""Synthetic HTTP contracts for Phase F reads; no live model, SMTP or Google calls."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import json
import unittest
from uuid import UUID, uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from app.main import app
from app.api.deps import get_optional_current_user
from app.core.config import settings
from app.db.models import (User, AgentRun, AgentRunStep, AuditCheckpoint, AuditEvent, Document,
    DocumentVersion, Equipment, KnowledgeGap, SensorReading)
from app.db.models.durable_execution import DurableExecution, ExecutionOperation
from app.db.session import get_db
from app.schemas.pid import PIDManifest
from app.schemas.query import QueryRequest
from app.schemas.verified_knowledge import GapSubmission, GapDecision
from app.services import ui_reads, knowledge_gaps
from app.services.approval import apply_decision
from app.services.audit import append_event
from app.services.governance import create_revision
from app.services.ingestion import write_json
from app.services.pid_regions import group_regions
from test_phase5a import state
import test_advanced_a1
from test_pid import page_info
from test_multimodal_pid import detection, visual

class UIReadTests(unittest.TestCase):
    def setUp(self):
        self.f = test_advanced_a1.VerifiedKnowledgeTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.db = self.f.session
        for model in (DurableExecution, ExecutionOperation, AuditCheckpoint):
            model.__table__.create(self.f.engine, checkfirst=True)
        self.actor = self.f.requester
        self.admin = User(username="ui-admin", role="admin", password_hash="unused")
        self.other = User(username="ui-other", role="requester", password_hash="unused")
        self.db.add_all([self.admin, self.other]); self.db.commit()
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_optional_current_user] = lambda: self.actor
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def get(self, path, **params):
        response = self.client.get(path, params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def execution(self, owner=None, status="COMPLETED", created=None):
        row = DurableExecution(id=uuid4(), user_id=(owner or self.f.requester).id,
            request={"query": "HIDDEN_PROMPT", "reasoning": "PRIVATE_CHAIN"}, status=status,
            selected_model=settings.primary_model, execution_path="EXISTING_AGENTIC_PATH",
            updated_at=created or ui_reads.now(), created_at=created or ui_reads.now())
        self.db.add(row); self.db.commit()
        return row

    def revision(self, owner=None, execution=None):
        request = QueryRequest(query="Review pump maintenance recommendation",
                               request_id=execution.id if execution else uuid4())
        revision = create_revision(self.db, request, state(), requester_user_id=(owner or self.f.requester).id)
        self.db.commit()
        return revision

    def decision(self, rev, decision="approve"):
        result = apply_decision(self.db, revision_id=rev.id, reviewer=self.f.reviewer, decision=decision)
        self.db.commit()
        return result

    def pid(self, restricted=False):
        root = settings.data_root
        data = BytesIO(); Image.new("RGB", (200, 100), "white").save(data, format="PNG")
        source = data.getvalue(); checksum = sha256(source).hexdigest()
        doc = Document(filename="synthetic.png", document_type="pid", classification="restricted" if restricted else "internal",
                       source_path="not-exposed", checksum=checksum)
        self.db.add(doc); self.db.flush()
        v = DocumentVersion(document_id=doc.id, source_sha256=checksum, status="pid_processed",
            ingestion_metadata={"kind": "pid", "request": {"title": "Synthetic drawing", "revision": "R1",
                                "access_scope": "restricted" if restricted else "internal"}, "source_filename": "synthetic.png"})
        self.db.add(v); self.db.commit()
        source_uri = "raw/pids/source/synthetic.png"
        source_path = root / source_uri; source_path.parent.mkdir(parents=True, exist_ok=True); source_path.write_bytes(source)
        image_uri = f"processed/pids/page_images/{v.id}/page_0001_rendered.png"
        image_path = root / image_uri; image_path.parent.mkdir(parents=True, exist_ok=True); image_path.write_bytes(source)
        page = page_info(source_image_uri=image_uri, processed_image_uri=image_uri)
        item = detection().model_copy(update={"source_image": image_uri})
        regions = group_regions([item], v.id)
        regions[0].visual_candidates = [visual("P-102A")]
        regions[0].visual_model = "qwen3.5:9b"
        region_uri = f"processed/pids/regions/{v.id}.json"
        artifact = {"document_id": str(doc.id), "document_version_id": str(v.id), "source_sha256": checksum,
                    "regions": [r.model_dump(mode="json") for r in regions]}
        write_json(root / region_uri, artifact)
        manifest = PIDManifest(document_id=doc.id, document_version_id=v.id, source_filename="synthetic.png",
            source_uri=source_uri, source_sha256=checksum, page_count=1, render_dpi=None, ocr_model=[],
            processed_at=ui_reads.now(), synthetic=True, warnings=[], pages=[page],
            ocr_json_uri="unused.json", region_json_uri=region_uri, ocr_detections=1, regions=1,
            equipment_tags=["P-101A"], instrument_tags=[])
        path = root / f"processed/pids/manifests/{v.id}.json"
        write_json(path, manifest.model_dump(mode="json"))
        return v, path, manifest, image_path

    def test_anonymous_read_routes_are_denied(self):
        self.actor = None
        for path in ("/executions", "/approvals", "/bi/operational", "/documents/pid",
                     "/equipment", "/sensors/channels?equipment_tag=P-101A", "/verified-knowledge", "/knowledge-gaps", "/audit/log"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)

    def test_reviewer_surfaces_remain_role_gated(self):
        for path in ("/approvals", "/approvals?view=history", "/bi/operational", "/audit/log"):
            self.assertEqual(self.client.get(path).status_code, 403)

    def test_lists_validate_pagination_and_ids(self):
        self.actor = self.admin
        for path in ("/executions", "/approvals", "/equipment", "/documents/pid", "/verified-knowledge", "/knowledge-gaps"):
            for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10001}):
                with self.subTest(path=path, params=params):
                    self.assertEqual(self.client.get(path, params=params).status_code, 422)
        for path in ("/executions/invalid", "/documents/pid/invalid", "/approvals/invalid", "/verified-knowledge/invalid"):
            self.assertEqual(self.client.get(path).status_code, 422)

    def test_invalid_ranges(self):
        self.actor = self.admin
        for path in ("/executions", "/approvals", "/audit/log", "/sensors/readings", "/maintenance/history"):
            for start, end in (("2026-01-02", "2026-01-01"), ("2026-01-01", "2026-01-01"), ("2024-01-01", "2026-01-01")):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path, params={"start": start, "end": end}).status_code, 422)
        for params in ({"range": "custom"}, {"range": "bad"}, {"range": "24h", "start": "2026-01-01"}):
            self.assertEqual(self.client.get("/bi/operational", params=params).status_code, 422)

    def test_execution_ownership_list_and_detail(self):
        own = self.execution()
        other = self.execution(self.other)
        self.assertEqual([i["execution_id"] for i in self.get("/executions").json()["items"]], [str(own.id)])
        self.assertEqual(self.client.get(f"/executions/{other.id}").status_code, 403)
        self.assertEqual(self.client.get(f"/executions/{uuid4()}").status_code, 403)
        self.actor = self.f.reviewer
        self.assertEqual(self.get("/executions").json()["items"], [])
        self.assertEqual(self.client.get(f"/executions/{own.id}").status_code, 403)
        self.actor = self.admin
        self.assertEqual(len(self.get("/executions").json()["items"]), 2)
        self.get(f"/executions/{other.id}")

    def test_execution_pagination_filters_and_timeline_safety(self):
        at = datetime(2026, 1, 2, tzinfo=timezone.utc)
        a = self.execution(status="FAILED", created=at)
        b = self.execution(created=at + timedelta(days=1))
        self.db.add_all([ExecutionOperation(execution_id=a.id, key=key, status="COMPLETED", attempts=1,
                        result={"private_reasoning": "PRIVATE_CHAIN", "prompt": "HIDDEN_PROMPT", "secret": "TOKEN"},
                        started_at=at, finished_at=at) for key in ("node:router", "tool:router:0:retrieve_documents:hash")])
        self.db.commit()
        first = self.get("/executions", limit=1).json()
        second = self.get("/executions", limit=1, offset=first["next_offset"]).json()
        self.assertEqual([first["items"][0]["execution_id"], second["items"][0]["execution_id"]], [str(b.id), str(a.id)])
        self.assertFalse(second["has_more"])
        filtered = self.get("/executions", status="FAILED", start=at.isoformat(), end=(at+timedelta(days=1)).isoformat()).json()
        self.assertEqual(filtered["sample_size"], 1)
        result = self.get(f"/executions/{a.id}", limit=1)
        for forbidden in ("PRIVATE_CHAIN", "HIDDEN_PROMPT", "TOKEN", "result", "checkpoint", "request"):
            self.assertNotIn('"' + forbidden + '"', result.text)
        self.assertTrue(result.json()["timeline"]["has_more"])
        self.assertEqual(result.json()["receipt_status_counts"], {"COMPLETED": 2})
        self.assertEqual(self.get(f"/executions/{a.id}", offset=1).json()["timeline"]["items"][0]["tool"], "retrieve_documents")

    def test_execution_uses_bound_revision_not_an_unrelated_decision(self):
        row = self.execution(status="WAITING_APPROVAL")
        first = self.revision(execution=row)
        request = QueryRequest(query="Review pump maintenance recommendation", request_id=row.id)
        second = create_revision(self.db, request, state("S7", summary="Different revision"),
                                 requester_user_id=self.f.requester.id)
        self.db.commit(); self.decision(second)
        result = self.get(f"/executions/{row.id}").json()
        self.assertEqual(result["action_revision_id"], str(first.id))
        self.assertEqual(result["governance_status"], "PENDING_REVIEW")
        self.assertFalse(result["resume_available"])

    def test_knowledge_history_is_bounded(self):
        item = self.f.candidate()
        for index in range(501):
            append_event(self.db, event_type="KNOWLEDGE_CANDIDATE_CREATED", actor_id=self.f.requester.id,
                actor_kind="user", action_revision_id=item.approval_revision_id, payload={"synthetic": index})
        self.db.commit()
        self.actor = self.admin
        history = self.get(f"/verified-knowledge/{item.id}/history").json()
        self.assertTrue(history["truncated"])
        self.assertEqual(len(history["events"]), 500)

    def test_resume_waits_for_real_decision(self):
        row = self.execution(status="WAITING_APPROVAL")
        rev = self.revision(execution=row)
        self.assertFalse(self.get(f"/executions/{row.id}").json()["resume_available"])
        self.decision(rev)
        self.assertTrue(self.get(f"/executions/{row.id}").json()["resume_available"])
        row.retry_class = "FAIL_CLOSED"; self.db.commit()
        self.assertFalse(self.get(f"/executions/{row.id}").json()["resume_available"])

    def test_approval_queue_history_decisions_and_link(self):
        execution = self.execution(status="WAITING_APPROVAL")
        approved = self.revision(execution=execution)
        pending = self.revision()
        self.revision(owner=self.f.reviewer)
        decision = self.decision(approved)
        self.actor = self.f.reviewer
        queue = self.get("/approvals").json()
        self.assertEqual([i["action_revision_id"] for i in queue], [str(pending.id)])
        result = self.get("/approvals", view="history").json()[0]
        self.assertEqual(result["execution_id"], str(execution.id))
        self.assertEqual(result["reviewer_id"], str(self.f.reviewer.id))
        self.assertEqual(result["requester_user_id"], str(self.f.requester.id))
        self.assertEqual(result["decisions"][0]["decision_id"], str(decision.id))
        self.assertEqual(result["governance_status"], "APPROVED")
        self.assertEqual(self.get("/approvals", view="history", status="REJECTED").json(), [])
        first = self.get("/approvals", view="all", limit=1)
        second = self.get("/approvals", view="all", limit=1, offset=1)
        self.assertEqual(first.headers["X-Has-More"], "true")
        self.assertNotEqual(first.json()[0]["action_revision_id"], second.json()[0]["action_revision_id"])

    def test_approval_model_selection_is_not_inferred_from_configuration(self):
        rev = self.revision()
        self.actor = self.admin
        self.assertIsNone(self.get("/approvals").json()[0]["selected_model"])
        self.db.add(AgentRunStep(run_id=rev.originating_run_id, step_index=99, node_name="execution_metadata",
            usage={"execution": {"model_selected": "qwen3.5:4b"}})); self.db.commit()
        self.assertEqual(self.get("/approvals").json()[0]["selected_model"], "qwen3.5:4b")

    def test_approval_expiry_revocation_matches_authority(self):
        rev = self.revision()
        with patch.object(settings, "approval_validity_seconds", .000001):
            self.decision(rev)
        self.actor = self.admin
        self.assertEqual(self.get("/approvals", view="history").json()[0]["governance_status"], "EXPIRED")
        revoked = self.revision(); self.decision(revoked); self.decision(revoked, "revoke")
        self.assertEqual(len(self.get("/approvals", view="history", status="REVOKED").json()), 1)

    def test_empty_dashboard_and_presets(self):
        self.actor = self.admin
        for period in ("24h", "7d", "30d"):
            data = self.get("/bi/operational", range=period).json()
            self.assertEqual(data["query_volume"]["sample_size"], 0)
            self.assertIsNone(data["model_routing"]["counts"])
            self.assertIsNone(data["escalations"]["count"])
            self.assertIsNone(data["approval_latency_seconds"]["mean"])
            self.assertIsNone(data["service_status"])
            self.assertIn("as_of", data)

    def test_dashboard_populated_filtered_recorded_metadata(self):
        at = datetime(2026, 3, 1, tzinfo=timezone.utc)
        for index, model in enumerate(("qwen3.5:4b", "qwen3.5:9b")):
            run = AgentRun(id=uuid4(), status="completed", created_at=at, model=model)
            self.db.add(run); self.db.flush()
            self.db.add(AgentRunStep(run_id=run.id, step_index=0, node_name="execution_metadata",
                usage={"execution": {"model_selected": model, "escalated": bool(index),
                                     "evidence_sufficiency": {"state": "SUFFICIENT" if index else "PARTIAL"},
                                     "reasoning": "PRIVATE_CHAIN"}}))
        self.db.commit()
        self.actor = self.admin
        result = self.get("/bi/operational", range="custom", start=at.isoformat(), end=(at+timedelta(days=1)).isoformat())
        data = result.json()
        self.assertEqual(data["query_volume"]["sample_size"], 2)
        self.assertEqual(data["model_routing"]["counts"], {"qwen3.5:4b": 1, "qwen3.5:9b": 1})
        self.assertEqual(data["escalations"], {"count": 1, "sample_size": 2})
        self.assertEqual(data["evidence_sufficiency"]["counts"], {"SUFFICIENT": 1, "PARTIAL": 1})
        self.assertNotIn("PRIVATE_CHAIN", result.text)
        empty = self.get("/bi/operational", range="custom", start=(at+timedelta(days=1)).isoformat(), end=(at+timedelta(days=2)).isoformat()).json()
        self.assertEqual(empty["query_volume"]["sample_size"], 0)

    def test_dashboard_truncation_is_explicit(self):
        self.db.add_all([AgentRun(id=uuid4(), status="completed") for _ in range(1001)]); self.db.commit()
        self.actor = self.admin
        data = self.get("/bi/operational").json()
        self.assertTrue(data["samples"]["runs"]["truncated"])
        self.assertEqual(data["query_volume"]["sample_size"], 1000)
        self.assertIsNone(data["escalations"]["count"])

    def test_dashboard_approval_counts_real_latency(self):
        execution = self.execution(status="WAITING_APPROVAL")
        rev = self.revision(execution=execution)
        self.decision(rev)
        self.revision()
        self.actor = self.admin
        data = self.get("/bi/operational").json()
        self.assertEqual(data["pending_approvals"]["count"], 1)
        self.assertEqual(data["approval_outcomes"]["counts"], {"APPROVE": 1})
        self.assertEqual(data["approval_latency_seconds"]["sample_size"], 1)
        self.assertGreaterEqual(data["approval_latency_seconds"]["mean"], 0)
        self.assertEqual(data["execution_status"]["counts"], {"WAITING_APPROVAL": 1})

    def test_pid_empty_unknown_and_scope(self):
        self.assertEqual(self.get("/documents/pid").json()["items"], [])
        self.assertEqual(self.client.get(f"/documents/pid/{uuid4()}").status_code, 404)
        v, _, _, _ = self.pid(restricted=True)
        self.assertEqual(self.get("/documents/pid").json()["items"], [])
        self.assertEqual(self.client.get(f"/documents/pid/{v.id}").status_code, 404)
        self.assertEqual(self.client.get(f"/documents/pid/{v.id}/pages/1/image").status_code, 404)

    def test_pid_regions_conflicts_provenance_image(self):
        v, _, _, _ = self.pid()
        listing = self.get("/documents/pid").json()
        self.assertEqual(listing["items"][0]["revision"], "R1")
        self.assertEqual(listing["items"][0]["page_count"], 1)
        result = self.get(f"/documents/pid/{v.id}").json()
        region = result["regions"]["items"][0]
        self.assertEqual(region["visual_candidates"][0]["tag"], "P-102A")
        self.assertTrue(region["conflicts"]); self.assertTrue(region["human_review_required"])
        self.assertEqual(region["source_sha256"], v.source_sha256)
        self.assertIn("valve open/closed", result["limitation"])
        image = self.get(result["pages"][0]["image_url"])
        self.assertEqual(image.headers["content-type"], "image/png")
        self.assertEqual(image.headers["x-content-type-options"], "nosniff")
        self.assertEqual(image.headers["cache-control"], "no-store")
        self.assertEqual(self.get(f"/documents/pid/{v.id}", offset=1).json()["regions"]["items"], [])
        self.assertEqual(self.client.get(f"/documents/pid/{v.id}", params={"page": 2}).status_code, 404)

    def test_pid_registry_lookup_is_reused_only_within_one_read(self):
        v, path, manifest, _ = self.pid()
        region_path = settings.data_root / manifest.region_json_uri
        artifact = json.loads(region_path.read_text())
        duplicate = dict(artifact["regions"][0], region_id=str(uuid4()))
        artifact["regions"].append(duplicate)
        write_json(region_path, artifact)
        write_json(path, manifest.model_copy(update={"regions": 2}).model_dump(mode="json"))
        with patch("app.services.pid_fusion.registry_evidence", return_value=None) as lookup:
            self.get(f"/documents/pid/{v.id}")
            self.assertEqual(lookup.call_count, 1)  # Shared OCR tag; conflicting visual overlaps that OCR.
            self.get(f"/documents/pid/{v.id}")
            self.assertEqual(lookup.call_count, 2)

    def test_pid_traversal_manifest_and_image_binding(self):
        v, path, manifest, _ = self.pid()
        for uri in ("../../secret", "/etc/passwd", "C:/secret", f"processed/pids/page_images/{uuid4()}/page_0001_rendered.png"):
            write_json(path, manifest.model_copy(update={"pages": [manifest.pages[0].model_copy(update={"source_image_uri": uri})]}).model_dump(mode="json"))
            self.assertEqual(self.client.get(f"/documents/pid/{v.id}/pages/1/image").status_code, 409)
        for uri in ("../../secret", "/etc/passwd", "raw/pids/source/synthetic.png"):
            write_json(path, manifest.model_copy(update={"region_json_uri": uri}).model_dump(mode="json"))
            self.assertEqual(self.client.get(f"/documents/pid/{v.id}").status_code, 409)

    def test_pid_symlink_source_hash_and_missing_artifact(self):
        v, path, manifest, image_path = self.pid()
        image_path.unlink()
        try:
            image_path.symlink_to(self.f.source)
        except OSError:
            self.skipTest("symlink requires Linux")
        self.assertEqual(self.client.get(f"/documents/pid/{v.id}/pages/1/image").status_code, 409)
        (settings.data_root / manifest.source_uri).write_bytes(b"changed")
        self.assertEqual(self.client.get(f"/documents/pid/{v.id}").status_code, 409)
        path.unlink()
        data = self.get("/documents/pid").json()["items"][0]
        self.assertIsNone(data["page_count"]); self.assertFalse(data["artifacts_available"])

    def test_equipment_and_channels_pagination_no_invented_thresholds(self):
        self.db.add(Equipment(equipment_tag="P-999", name="Another", equipment_type="pump")); self.db.commit()
        first = self.get("/equipment", q="P-", limit=1).json()
        second = self.get("/equipment", q="P-", limit=1, offset=1).json()
        self.assertTrue(first["has_more"]); self.assertNotEqual(first["items"][0]["id"], second["items"][0]["id"])
        self.assertEqual(self.get("/equipment", q="%").json()["items"], [])
        data = self.get("/sensors/channels", equipment_tag="P-101A").json()
        self.assertEqual(data["sample_size"], 1)
        self.assertIsNone(data["items"][0]["thresholds"])
        self.assertEqual(data["items"][0]["unit"], "mm/s")
        self.assertEqual(self.get("/sensors/channels", equipment_tag="unknown").json()["items"], [])

    def test_sensor_series_latest_and_maintenance_reuse(self):
        rows = self.get("/sensors/readings", equipment_tag="P-101A", limit=1).json()["results"]
        self.assertEqual(len(rows), 1)
        latest = self.get("/sensors/latest", equipment_tag="P-101A").json()["results"]
        self.assertEqual(len(latest), 1); self.assertEqual(latest[0]["value"], 3)
        records = self.get("/maintenance/history", equipment_tag="P-101A", limit=1).json()["results"]
        self.assertEqual(records[0]["work_order_id"], "WO-1")
        self.assertEqual(self.get("/sensors/readings", equipment_tag="missing").json()["results"], [])

    def test_knowledge_filter_pagination_and_role_history(self):
        candidate = self.f.candidate()
        stale = self.f.candidate()
        self.f.decide(stale, "stale")
        self.assertEqual(len(self.get("/verified-knowledge", status="CANDIDATE").json()), 1)
        self.assertEqual(len(self.get("/verified-knowledge", status="STALE").json()), 1)
        response = self.get("/verified-knowledge", limit=1)
        self.assertEqual(response.headers["X-Has-More"], "true")
        page = self.get("/verified-knowledge", limit=1, offset=response.headers["X-Next-Offset"])
        self.assertNotEqual(response.json()[0]["knowledge_id"], page.json()[0]["knowledge_id"])
        self.assertEqual(self.client.get(f"/verified-knowledge/{candidate.id}/history").status_code, 403)
        self.actor = self.f.reviewer
        history = self.get(f"/verified-knowledge/{candidate.id}/history").json()
        self.assertIn("lineage", history)
        self.assertEqual(self.client.get("/verified-knowledge", params={"status": "invented"}).status_code, 422)

    def test_knowledge_stale_source_never_lists_verified(self):
        item = self.f.verified()
        self.f.source.write_bytes(b"changed")
        self.assertEqual(self.get("/verified-knowledge", status="VERIFIED").json(), [])
        self.assertEqual(self.get("/verified-knowledge", status="STALE").json()[0]["knowledge_id"], str(item.id))

    def test_gap_status_pagination_and_real_transitions(self):
        ids = []
        for index in range(3):
            data = knowledge_gaps.submit(self.db, GapSubmission(subject=f"P-{index}", gap_type="missing_threshold",
                         required_evidence="Documented threshold"), self.f.requester)
            ids.append(data["gap_id"])
        knowledge_gaps.transition(self.db, ids[0], GapDecision(comment="Review"), self.f.reviewer, "assign")
        self.db.commit()
        self.assertEqual(len(self.get("/knowledge-gaps", status="UNDER_REVIEW").json()), 1)
        response = self.get("/knowledge-gaps", status="OPEN", limit=1)
        self.assertEqual(response.headers["X-Has-More"], "true")
        self.assertNotEqual(response.json()[0]["gap_id"], self.get("/knowledge-gaps", status="OPEN", offset=1).json()[0]["gap_id"])
        self.assertEqual(self.get("/knowledge-gaps", status="DISMISSED").json(), [])

    def test_gap_old_decision_overrides_recent_detected_gap(self):
        from app.services.canonicalization import canonical_hash
        gap = knowledge_gaps.submit(self.db, GapSubmission(subject="old", gap_type="missing_rule",
            required_evidence="Documented rule"), self.f.requester)
        knowledge_gaps.transition(self.db, gap["gap_id"], GapDecision(comment="Duplicate"), self.f.reviewer, "dismiss")
        old = self.db.get(KnowledgeGap, gap["gap_id"])
        old.updated_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        for index in range(501):
            self.db.add(KnowledgeGap(id=canonical_hash(index), subject="recent", gap_type="missing_rule",
                required_evidence="rule", related_evidence=[], origin="manual_submission", access_scope="internal",
                status="OPEN", updated_at=ui_reads.now()))
        run = AgentRun(id=uuid4(), status="completed"); self.db.add(run); self.db.flush()
        self.db.add(AgentRunStep(run_id=run.id, node_name="execution_metadata", step_index=0,
            usage={"execution": {"knowledge_gaps": [{"gap_id": gap["gap_id"], "subject": "old", "gap_type": "missing_rule", "required_evidence": "rule", "related_evidence": [], "status": "OPEN"}]}}))
        self.db.commit()
        result = self.get("/knowledge-gaps", status="DISMISSED").json()
        self.assertEqual(result[0]["gap_id"], gap["gap_id"])
        self.assertEqual(result[0]["status"], "DISMISSED")

    def test_knowledge_empty_filtered_page_exposes_continuation(self):
        for index in range(3):
            self.f.candidate()
        self.assertEqual(self.get("/verified-knowledge", status="REVOKED").json(), [])
        page = self.get("/verified-knowledge", limit=1)
        self.assertIn("X-Next-Offset", page.headers)
        self.assertEqual(page.headers["X-Scan-Limit"], "100")

    def test_audit_knowledge_object_filter_and_empty_time_range(self):
        item = self.f.candidate()
        self.actor = self.admin
        data = self.get("/audit/log", knowledge_id=item.id).json()
        self.assertTrue(data)
        self.assertTrue(all(row["action_revision_id"] == str(item.approval_revision_id) for row in data))
        self.assertEqual(self.get("/audit/log", start="2000-01-01", end="2000-01-02").json(), [])

    def test_audit_filters_cursor_redaction_and_verification(self):
        rev = self.revision(); self.decision(rev)
        append_event(self.db, event_type="LOGIN_SUCCESS", actor_id=self.f.requester.id, actor_kind="user",
                     payload={"secret": "HIDDEN_SECRET", "reasoning": "PRIVATE_CHAIN"}); self.db.commit()
        self.actor = self.admin
        response = self.get("/audit/log", limit=1)
        first = response.json()[0]
        self.assertEqual(first["payload"], {})
        self.assertNotIn("HIDDEN_SECRET", response.text); self.assertNotIn("PRIVATE_CHAIN", response.text)
        self.assertEqual(len(first["event_hash"]), 64)
        earlier = self.get("/audit/log", before_sequence=first["sequence_number"], limit=1).json()[0]
        self.assertLess(earlier["sequence_number"], first["sequence_number"])
        filtered = self.get("/audit/log", event_type="APPROVAL_DECISION_APPROVE", approval_id=rev.id).json()
        self.assertEqual(len(filtered), 1)
        self.assertEqual(len(self.get("/audit/log", execution_id=rev.request_id).json()), 1)
        append_event(self.db, event_type="HANDOVER_GENERATED", actor_id=self.f.requester.id, actor_kind="user",
                     payload={"run_id": str(rev.request_id)}); self.db.commit()
        self.assertEqual(len(self.get("/audit/log", execution_id=rev.request_id).json()), 2)
        self.assertEqual(len(self.get("/audit/log", user_id=self.f.requester.id, event_type="LOGIN_SUCCESS").json()), 1)
        self.assertEqual(self.get("/audit/log", knowledge_id=uuid4()).json(), [])
        self.assertTrue(self.get("/audit/verify").json()["valid"])

class PostgreSQLReadTests(unittest.TestCase):
    @unittest.skipUnless(__import__("os").environ.get("WORKBENCH_TEST_POSTGRES") == "1",
                         "Real PostgreSQL integration not enabled")
    def test_read_projections_from_0017(self):
        from pathlib import Path
        from types import SimpleNamespace
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        from sqlalchemy.orm import Session
        from app.services import industrial_bi, pid_reads
        schema = "test_ui_reads_" + uuid4().hex
        admin = create_engine(settings.database_url)
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        def cleanup():
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()
        self.addCleanup(cleanup)
        url = make_url(settings.database_url).update_query_dict({"options": f"-csearch_path={schema}"})
        engine = create_engine(url); self.addCleanup(engine.dispose)
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with patch.object(settings, "database_url", url.render_as_string(hide_password=False)):
            command.upgrade(config, "0017_accounts_recovery")
            command.upgrade(config, "head")
            command.check(config)
        with Session(engine) as db:
            requester = User(username="pg-requester", role="requester", password_hash="unused")
            reviewer = User(username="pg-reviewer", role="reviewer", password_hash="unused")
            db.add_all([requester, reviewer]); db.commit()
            fixture = SimpleNamespace(db=db, f=SimpleNamespace(requester=requester))
            execution = UIReadTests.execution(fixture, status="WAITING_APPROVAL")
            revision = UIReadTests.revision(fixture, execution=execution)
            pending = ui_reads.approvals(db, reviewer, "pending", None, 50, 0)
            self.assertEqual(pending[0]["action_revision_id"], revision.id)
            self.assertFalse(ui_reads.execution_detail(db, execution.id, requester, 50, 0)["resume_available"])
            apply_decision(db, revision_id=revision.id, reviewer=reviewer, decision="approve"); db.commit()
            history = ui_reads.approvals(db, reviewer, "history", None, 50, 0)
            self.assertEqual(history[0]["governance_status"], "APPROVED")
            self.assertTrue(ui_reads.execution_detail(db, execution.id, requester, 50, 0)["resume_available"])
            report = industrial_bi.dashboard(db, ui_reads.now() - timedelta(days=1), ui_reads.now())
            self.assertEqual(report["approval_outcomes"]["counts"], {"APPROVE": 1})
            self.assertEqual(report["approval_latency_seconds"]["sample_size"], 1)
            self.assertEqual(pid_reads.listing(db, 50, 0)["items"], [])
            doc = Document(filename="drawing.png", document_type="pid", classification="internal", source_path="unused")
            db.add(doc); db.flush()
            db.add(DocumentVersion(document_id=doc.id, source_sha256="f"*64, status="pid_processing",
                ingestion_metadata={"kind": "pid", "request": {"access_scope": "internal"}})); db.commit()
            self.assertEqual(pid_reads.listing(db, 50, 0)["sample_size"], 1)
