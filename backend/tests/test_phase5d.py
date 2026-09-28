"""Phase 5D cryptographic evidence integrity checks. SQLite verifies
deterministic hashing/binding/verification logic and ORM-level immutability,
NOT PostgreSQL raw-SQL immutability -- see test_phase5d_postgres.py for that.

Evidence INTEGRITY is not evidence CORRECTNESS, OCR confidence, authorization,
or plant-state truth -- several tests below exist specifically to prove that
distinction in code, not just assert it in docs."""
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.agents.evidence import csv_row_evidence, document_chunk_evidence, pid_region_evidence, sensor_window_evidence
from app.agents.registry import list_tools
from app.core.security import hash_password
from app.db.base import Base
from app.db.models import (
    ActionRevision, Agent, AgentAction, AgentRun, AgentRunStep, ApprovalDecision, AuditChainHead,
    AuditEvent, AuthSession, Document, DocumentVersion, Equipment, EvidenceManifest, EvidenceManifestItem,
    GovernanceRequest, MaintenanceRecord, SensorReading, User,
)
from app.db.session import get_db
from app.main import app
from app.schemas.query import QueryRequest
from app.services.approval import apply_decision, release_advisory
from app.services.canonicalization import canonical_hash
from app.services.governance import EvidenceIntegrityFailure, ReleaseNotAllowed, assert_release_allowed, govern_response
from app.services.evidence_integrity import get_evidence_integrity_status, verify_manifest

# DocumentVersion is deliberately NOT created via Base.metadata.create_all
# below: its ingestion_metadata/warnings columns are a raw postgresql.JSONB
# (not the SQLite-compatible JSON().with_variant pattern most later-phase
# tables use), which SQLite's DDL compiler cannot render. A hand-written
# CREATE TABLE (see setUp) sidesteps DDL compilation entirely; ORM read/write
# of the JSONB-typed columns works fine against SQLite once the table exists
# (verified: SQLAlchemy's JSON value processing, unlike DDL rendering, is not
# PostgreSQL-specific).
TABLES = [model.__table__ for model in (
    User, Agent, AgentAction, AgentRun, AgentRunStep, GovernanceRequest, ActionRevision,
    AuthSession, ApprovalDecision, AuditChainHead, AuditEvent, EvidenceManifest, EvidenceManifestItem,
    Equipment, Document, MaintenanceRecord, SensorReading,
)]


def _state(evidence, schema="S7", **output):
    return {"run_id": str(uuid4()), "query": "Review pump operating recommendation", "route": "safety",
            "agent_result": {"schema": schema, "output": output or {"summary": "Proposal"}},
            "human_approval_required": False, "evidence": evidence, "warnings": [], "step_records": []}


def _dump(ref) -> dict:
    return ref.model_dump(mode="json")


class EvidenceIntegrityTests(unittest.TestCase):
    """Direct service-level checks (no HTTP layer)."""

    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine, tables=TABLES)
        self.session = Session(self.engine)
        self.session.execute(text(
            "CREATE TABLE document_versions (id TEXT PRIMARY KEY, created_at TEXT, document_id TEXT, "
            "source_sha256 TEXT UNIQUE, status TEXT, chunk_count INTEGER, ingestion_metadata TEXT, warnings TEXT)"
        ))
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)

        self.requester = User(username="d-requester", role="requester", password_hash=hash_password("r"))
        self.reviewer = User(username="d-reviewer", role="reviewer", password_hash=hash_password("v"))
        self.session.add_all([self.requester, self.reviewer])

        self.equipment = Equipment(equipment_tag="P-101A", name="Pump P-101A", equipment_type="pump")
        self.session.add(self.equipment)
        self.session.commit()

        self.document = Document(filename="manual.pdf", document_type="manual", source_path="s3://manual.pdf",
                                 classification="internal")
        self.session.add(self.document)
        self.session.commit()
        self.document_version = DocumentVersion(document_id=self.document.id, source_sha256="a" * 64,
                                                status="processed", chunk_count=1, ingestion_metadata={})
        self.session.add(self.document_version)
        self.session.commit()

        self.maintenance_record = MaintenanceRecord(
            equipment_id=self.equipment.id, raw_equipment_tag="P-101A", work_order_id="WO-1",
            maintenance_type="corrective", failure_mode="bearing", description="Replaced bearing",
            source_filename="maint.csv", source_sha256="c" * 64, source_row_number=1, raw_row={"row": 1},
        )
        self.session.add(self.maintenance_record)

        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.readings = [
            SensorReading(equipment_id=self.equipment.id, sensor_tag="P-101A-VIB", sensor_type="vibration",
                         value=1.0 + i, unit="mm/s", quality="good", timestamp=now + timedelta(hours=i),
                         source_filename="sensors.csv", source_sha256="d" * 64, source_row_number=i + 1)
            for i in range(3)
        ]
        self.session.add_all(self.readings)
        self.session.commit()

    def make_revision(self, evidence, *, requester_user_id=None):
        request = QueryRequest(query="Review pump recommendation", request_id=uuid4())
        requester_user_id = requester_user_id if requester_user_id is not None else self.requester.id
        return govern_response(self.session, request, _state(evidence), requester_user_id=requester_user_id)

    def sensor_citations(self, readings):
        return [{"source_filename": r.source_filename, "source_sha256": r.source_sha256,
                "source_row_number": r.source_row_number} for r in readings]

    # -- Real app.agents.evidence factory functions, dumped to dicts exactly
    # as app.services.governance._proposal_payload would store them --
    # guarantees every test evidence item is a genuinely valid EvidenceRef,
    # not a hand-rolled approximation of one.

    def document_chunk(self, *, quote="original text", chunk_id="chunk-1", document_version_id=None):
        return _dump(document_chunk_evidence(
            chunk_id=chunk_id, document_id=str(self.document.id),
            document_version_id=document_version_id or str(self.document_version.id),
            source_filename="manual.pdf", source_sha256=self.document_version.source_sha256,
            section_path=["1"], page_start=1, page_end=1, bounding_boxes=[], quote=quote,
        ))

    def pid_region(self, *, combined_text="P-101A", region_id="r1", confidence=0.95, ocr_status="unverified",
                   document_version_id=None):
        return _dump(pid_region_evidence(
            region_id=region_id, document_id=str(self.document.id),
            document_version_id=document_version_id or str(self.document_version.id),
            source_filename="pid.pdf", source_sha256=self.document_version.source_sha256,
            page=1, bbox=(0.0, 0.0, 1.0, 1.0), confidence=confidence, ocr_status=ocr_status,
            combined_text=combined_text,
        ))

    def csv_row(self, *, source_sha256, source_row_number):
        return _dump(csv_row_evidence(source_filename="data.csv", source_sha256=source_sha256,
                                      source_row_number=source_row_number))

    def sensor_window(self, *, citations, citation_label="P-101A vibration 2026-01-01 to 2026-01-02"):
        return _dump(sensor_window_evidence(
            source_filename="sensors.csv",
            source_sha256=citations[0]["source_sha256"] if citations else "0" * 64,
            citation_label=citation_label, provenance=citations,
        ))

    def document_chunk_raw(self, *, document_version_id, quote="original text", chunk_id="chunk-1"):
        """Unlike document_chunk() above, never falls back to a real
        document_version_id -- lets a test freeze evidence with an empty or
        nonexistent value verbatim, exactly as a forged/corrupted EvidenceRef
        would (Astra finding 1)."""
        return _dump(document_chunk_evidence(
            chunk_id=chunk_id, document_id=str(self.document.id), document_version_id=document_version_id,
            source_filename="manual.pdf", source_sha256=self.document_version.source_sha256,
            section_path=["1"], page_start=1, page_end=1, bounding_boxes=[], quote=quote,
        ))

    def fake_citation(self, row_number=999):
        """A citation that never resolves to any real SensorReading -- for
        Astra finding 2's unresolved-reading regressions."""
        return {"source_filename": "sensors.csv", "source_sha256": "9" * 64, "source_row_number": row_number}

    # -- HASHING -------------------------------------------------------------

    def test_same_evidence_same_item_hash(self):
        chunk = self.document_chunk()
        first = self.make_revision([chunk])
        second = self.make_revision([chunk])
        first_item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == first.action_revision_id).one()
        second_item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == second.action_revision_id).one()
        self.assertEqual(first_item.canonical_item_hash, second_item.canonical_item_hash)
        self.assertEqual(first_item.content_hash, second_item.content_hash)

    def test_changed_document_chunk_hash_changes(self):
        first = self.make_revision([self.document_chunk(quote="original text")])
        second = self.make_revision([self.document_chunk(quote="different text")])
        first_item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == first.action_revision_id).one()
        second_item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == second.action_revision_id).one()
        self.assertNotEqual(first_item.content_hash, second_item.content_hash)
        self.assertNotEqual(first_item.canonical_item_hash, second_item.canonical_item_hash)

    def test_changed_ocr_text_hash_changes(self):
        first = self.make_revision([self.pid_region(combined_text="P-101A")])
        second = self.make_revision([self.pid_region(combined_text="P-101B")])
        first_item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == first.action_revision_id).one()
        second_item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == second.action_revision_id).one()
        self.assertNotEqual(first_item.content_hash, second_item.content_hash)

    def test_changed_ocr_region_hash_changes(self):
        first = self.make_revision([self.pid_region(region_id="r1")])
        second = self.make_revision([self.pid_region(region_id="r2")])
        first_item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == first.action_revision_id).one()
        second_item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == second.action_revision_id).one()
        self.assertNotEqual(first_item.canonical_item_hash, second_item.canonical_item_hash)

    def test_changed_maintenance_record_hash_changes(self):
        ref = self.csv_row(source_sha256=self.maintenance_record.source_sha256,
                       source_row_number=self.maintenance_record.source_row_number)
        first = self.make_revision([ref])
        first_item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == first.action_revision_id).one()

        self.maintenance_record.description = "Replaced bearing AND seal"
        self.session.commit()

        second = self.make_revision([ref])
        second_item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == second.action_revision_id).one()
        self.assertNotEqual(first_item.content_hash, second_item.content_hash)

    def test_changed_sensor_reading_hash_changes(self):
        reading = self.readings[0]
        ref = self.csv_row(source_sha256=reading.source_sha256, source_row_number=reading.source_row_number)
        first = self.make_revision([ref])
        first_item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == first.action_revision_id).one()

        reading.value = 999.0
        self.session.commit()

        second = self.make_revision([ref])
        second_item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == second.action_revision_id).one()
        self.assertNotEqual(first_item.content_hash, second_item.content_hash)

    def test_changed_window_order_manifest_changes(self):
        forward = self.make_revision([self.sensor_window(citations=self.sensor_citations(self.readings))])
        backward = self.make_revision([self.sensor_window(citations=self.sensor_citations(list(reversed(self.readings))))])
        forward_item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == forward.action_revision_id).one()
        backward_item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == backward.action_revision_id).one()
        self.assertNotEqual(forward_item.content_hash, backward_item.content_hash)

    # -- BINDING ---------------------------------------------------------

    def test_revision_binds_exact_manifest(self):
        response = self.make_revision([self.document_chunk()])
        manifest = self.session.query(EvidenceManifest).filter_by(action_revision_id=response.action_revision_id).one()
        self.assertEqual(manifest.action_revision_id, response.action_revision_id)
        self.assertEqual(manifest.item_count, 1)
        result = verify_manifest(self.session, response.action_revision_id)
        self.assertTrue(result["valid"])
        self.assertEqual(result["manifest_id"], manifest.id)

    def test_manifest_substitution_detected(self):
        first = self.make_revision([self.document_chunk(quote="A")])
        second = self.make_revision([self.document_chunk(quote="B")])
        first_manifest = self.session.query(EvidenceManifest).filter_by(action_revision_id=first.action_revision_id).one()
        second_manifest = self.session.query(EvidenceManifest).filter_by(action_revision_id=second.action_revision_id).one()
        # Substitute revision A's manifest hash with revision B's -- a forged
        # "this manifest is actually the other one" attempt.
        self.session.execute(EvidenceManifest.__table__.update().where(EvidenceManifest.id == first_manifest.id)
                            .values(canonical_manifest_hash=second_manifest.canonical_manifest_hash)
                            .execution_options(synchronize_session=False))
        self.session.commit()
        result = verify_manifest(self.session, first.action_revision_id)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "manifest_hash_mismatch")

    def test_revision_a_manifest_cannot_satisfy_revision_b(self):
        first = self.make_revision([self.document_chunk(quote="A")])
        second = self.make_revision([self.document_chunk(quote="B")])
        manifest_a = self.session.query(EvidenceManifest).filter_by(action_revision_id=first.action_revision_id).one()
        manifest_b = self.session.query(EvidenceManifest).filter_by(action_revision_id=second.action_revision_id).one()
        self.assertNotEqual(manifest_a.id, manifest_b.id)
        result_a = verify_manifest(self.session, first.action_revision_id)
        result_b = verify_manifest(self.session, second.action_revision_id)
        self.assertEqual(result_a["manifest_id"], manifest_a.id)
        self.assertEqual(result_b["manifest_id"], manifest_b.id)
        self.assertNotEqual(result_a["manifest_id"], result_b["manifest_id"])

    def test_changed_evidence_requires_new_binding(self):
        chunk_a = self.document_chunk(quote="A")
        chunk_b = self.document_chunk(quote="B")
        first = govern_response(self.session, QueryRequest(query="Review pump recommendation", request_id=uuid4()),
                                _state([chunk_a]), requester_user_id=self.requester.id)
        second = govern_response(self.session, QueryRequest(query="Review pump recommendation", request_id=uuid4()),
                                 _state([chunk_b]), requester_user_id=self.requester.id)
        self.assertNotEqual(first.action_revision_id, second.action_revision_id)
        manifest_first = self.session.query(EvidenceManifest).filter_by(action_revision_id=first.action_revision_id).one()
        manifest_second = self.session.query(EvidenceManifest).filter_by(action_revision_id=second.action_revision_id).one()
        self.assertNotEqual(manifest_first.canonical_manifest_hash, manifest_second.canonical_manifest_hash)

    # -- IMMUTABILITY (ORM level; PostgreSQL raw-SQL in test_phase5d_postgres.py) --

    def test_orm_update_denied(self):
        response = self.make_revision([self.document_chunk()])
        manifest = self.session.query(EvidenceManifest).filter_by(action_revision_id=response.action_revision_id).one()
        manifest.item_count = 999
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.session.flush()
        self.session.rollback()

        item = self.session.query(EvidenceManifestItem).filter_by(manifest_id=manifest.id).one()
        item.content_hash = "0" * 64
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.session.flush()
        self.session.rollback()

    # -- VERIFICATION ---------------------------------------------------

    def test_valid_manifest_verifies(self):
        response = self.make_revision([self.document_chunk()])
        self.assertEqual(get_evidence_integrity_status(self.session, response.action_revision_id), "VERIFIED")

    def test_corrupted_item_fails(self):
        response = self.make_revision([self.document_chunk()])
        item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == response.action_revision_id).one()
        self.session.execute(EvidenceManifestItem.__table__.update().where(EvidenceManifestItem.id == item.id)
                            .values(content_hash="0" * 64).execution_options(synchronize_session=False))
        self.session.commit()
        result = verify_manifest(self.session, response.action_revision_id)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "item_hash_mismatch")
        self.assertEqual(get_evidence_integrity_status(self.session, response.action_revision_id), "FAILED")

    def test_corrupted_manifest_hash_fails(self):
        response = self.make_revision([self.document_chunk()])
        manifest = self.session.query(EvidenceManifest).filter_by(action_revision_id=response.action_revision_id).one()
        self.session.execute(EvidenceManifest.__table__.update().where(EvidenceManifest.id == manifest.id)
                            .values(canonical_manifest_hash="1" * 64).execution_options(synchronize_session=False))
        self.session.commit()
        result = verify_manifest(self.session, response.action_revision_id)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "manifest_hash_mismatch")

    def test_missing_manifest_fails(self):
        response = self.make_revision([self.document_chunk()])
        manifest = self.session.query(EvidenceManifest).filter_by(action_revision_id=response.action_revision_id).one()
        self.session.execute(EvidenceManifestItem.__table__.delete().where(EvidenceManifestItem.manifest_id == manifest.id))
        self.session.execute(EvidenceManifest.__table__.delete().where(EvidenceManifest.id == manifest.id))
        self.session.commit()
        result = verify_manifest(self.session, response.action_revision_id)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "manifest_missing")

    def test_legacy_unverified_not_mislabeled_verified(self):
        response = self.make_revision([self.document_chunk()])
        manifest = self.session.query(EvidenceManifest).filter_by(action_revision_id=response.action_revision_id).one()
        self.session.execute(EvidenceManifestItem.__table__.delete().where(EvidenceManifestItem.manifest_id == manifest.id))
        self.session.execute(EvidenceManifest.__table__.delete().where(EvidenceManifest.id == manifest.id))
        self.session.commit()
        status = get_evidence_integrity_status(self.session, response.action_revision_id)
        self.assertEqual(status, "LEGACY_UNVERIFIED")
        self.assertNotEqual(status, "VERIFIED")

    # -- RELEASE --------------------------------------------------------

    def approve(self, revision_id):
        apply_decision(self.session, revision_id=revision_id, reviewer=self.reviewer, decision="approve")
        self.session.commit()

    def test_approved_valid_integrity_can_release(self):
        response = self.make_revision([self.document_chunk()])
        self.approve(response.action_revision_id)
        detail = release_advisory(self.session, response.action_revision_id, actor=self.reviewer)
        self.assertEqual(detail["governance_status"], "RELEASED")

    def test_approved_corrupted_evidence_cannot_release(self):
        response = self.make_revision([self.document_chunk()])
        self.approve(response.action_revision_id)
        item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == response.action_revision_id).one()
        self.session.execute(EvidenceManifestItem.__table__.update().where(EvidenceManifestItem.id == item.id)
                            .values(content_hash="0" * 64).execution_options(synchronize_session=False))
        self.session.commit()
        with self.assertRaises(EvidenceIntegrityFailure):
            release_advisory(self.session, response.action_revision_id, actor=self.reviewer)
        self.session.rollback()
        # A plain ReleaseNotAllowed catch also works -- EvidenceIntegrityFailure subclasses it.
        with self.assertRaises(ReleaseNotAllowed):
            assert_release_allowed(self.session, response.action_revision_id)

    def test_approved_wrong_manifest_cannot_release(self):
        response = self.make_revision([self.document_chunk()])
        self.approve(response.action_revision_id)
        manifest = self.session.query(EvidenceManifest).filter_by(action_revision_id=response.action_revision_id).one()
        self.session.execute(EvidenceManifest.__table__.update().where(EvidenceManifest.id == manifest.id)
                            .values(canonical_manifest_hash="f" * 64).execution_options(synchronize_session=False))
        self.session.commit()
        with self.assertRaises(EvidenceIntegrityFailure):
            release_advisory(self.session, response.action_revision_id, actor=self.reviewer)

    # -- OCR: integrity != correctness/confidence/topology ---------------

    def test_ocr_integrity_does_not_imply_topology_or_confidence(self):
        # A LOW-confidence, "ambiguous" OCR region still passes INTEGRITY
        # verification -- integrity only proves "this is the exact recognized
        # text that was frozen", never that the OCR read it correctly, nor
        # anything about physical topology/connectivity/valve state.
        response = self.make_revision([self.pid_region(combined_text="P-101A", confidence=0.05, ocr_status="ambiguous")])
        self.assertEqual(get_evidence_integrity_status(self.session, response.action_revision_id), "VERIFIED")
        item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == response.action_revision_id).one()
        for forbidden in ("topology", "connectivity", "isolated", "valve_state", "flow_direction"):
            self.assertNotIn(forbidden, item.provenance)

    # -- SENSOR: reorder/modification detected ---------------------------

    def test_reordered_sensor_readings_detected_on_reverify(self):
        response = self.make_revision([self.sensor_window(citations=self.sensor_citations(self.readings))])
        self.assertEqual(get_evidence_integrity_status(self.session, response.action_revision_id), "VERIFIED")
        item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == response.action_revision_id).one()
        # Corrupt the stored ORDER of citations directly (simulating a
        # reordered window) without touching content_hash -- re-verification
        # recomputes from the (now reordered) citations and must disagree.
        reordered_provenance = dict(item.provenance)
        reordered_provenance["citations"] = list(reversed(item.provenance["citations"]))
        self.session.execute(EvidenceManifestItem.__table__.update().where(EvidenceManifestItem.id == item.id)
                            .values(provenance=reordered_provenance).execution_options(synchronize_session=False))
        self.session.commit()
        result = verify_manifest(self.session, response.action_revision_id)
        self.assertFalse(result["valid"])
        # The provenance mutation itself is caught as an item hash mismatch
        # (provenance is part of the item's own canonical hash), which is a
        # strictly stronger detection than only checking source content.
        self.assertEqual(result["error_type"], "item_hash_mismatch")

    def test_modified_sensor_reading_detected_on_reverify(self):
        response = self.make_revision([self.sensor_window(citations=self.sensor_citations(self.readings))])
        self.assertEqual(get_evidence_integrity_status(self.session, response.action_revision_id), "VERIFIED")
        self.readings[0].value = 12345.0
        self.session.commit()
        result = verify_manifest(self.session, response.action_revision_id)
        self.assertFalse(result["valid"])
        # Astra repair: renamed from the generic "source_content_changed" to
        # "sensor_evidence_mismatch" for this evidence_type specifically.
        self.assertEqual(result["error_type"], "sensor_evidence_mismatch")

    # -- AUDIT ------------------------------------------------------------

    def test_manifest_creation_audited(self):
        response = self.make_revision([self.document_chunk()])
        manifest = self.session.query(EvidenceManifest).filter_by(action_revision_id=response.action_revision_id).one()
        row = self.session.query(AuditEvent).filter_by(event_type="EVIDENCE_MANIFEST_CREATED").one()
        self.assertEqual(row.action_revision_id, response.action_revision_id)
        self.assertEqual(row.payload["manifest_id"], str(manifest.id))
        self.assertEqual(row.payload["item_count"], 1)

    def test_integrity_success_audited_on_release(self):
        response = self.make_revision([self.document_chunk()])
        self.approve(response.action_revision_id)
        release_advisory(self.session, response.action_revision_id, actor=self.reviewer)
        row = self.session.query(AuditEvent).filter_by(event_type="EVIDENCE_INTEGRITY_VERIFIED").one()
        self.assertEqual(row.action_revision_id, response.action_revision_id)

    # -- ASTRA REPAIR REGRESSIONS: document-provenance / sensor-reading -----
    # fail-closed bypasses (docs/phase5d-validation.md, "Independent security
    # audit repair"). Both scenarios freeze SELF-CONSISTENT evidence (the
    # missing/unresolved fact is present from the moment the EvidenceRef was
    # created, not introduced by later corruption) -- exactly Astra's repro
    # shape: the item hash matches its own (bad) provenance, so only live
    # re-verification against the authoritative source can catch it.

    def test_document_evidence_empty_version_id_fails(self):
        response = self.make_revision([self.document_chunk_raw(document_version_id="")])
        result = verify_manifest(self.session, response.action_revision_id)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "document_provenance_missing")
        self.assertEqual(get_evidence_integrity_status(self.session, response.action_revision_id), "FAILED")

    def test_document_evidence_nonexistent_version_id_fails(self):
        response = self.make_revision([self.document_chunk_raw(document_version_id=str(uuid4()))])
        result = verify_manifest(self.session, response.action_revision_id)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "document_version_unresolved")

    def test_document_evidence_valid_version_and_hash_verifies(self):
        response = self.make_revision([self.document_chunk_raw(document_version_id=str(self.document_version.id))])
        result = verify_manifest(self.session, response.action_revision_id)
        self.assertTrue(result["valid"])
        self.assertEqual(get_evidence_integrity_status(self.session, response.action_revision_id), "VERIFIED")

    def test_sensor_manifest_nonexistent_reading_fails(self):
        response = self.make_revision([self.sensor_window(citations=[self.fake_citation()])])
        result = verify_manifest(self.session, response.action_revision_id)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "sensor_reading_unresolved")

    def test_sensor_manifest_one_missing_reading_in_otherwise_valid_window_fails(self):
        citations = self.sensor_citations(self.readings) + [self.fake_citation()]
        response = self.make_revision([self.sensor_window(citations=citations)])
        result = verify_manifest(self.session, response.action_revision_id)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "sensor_reading_unresolved")

    def test_sensor_resolved_count_below_manifest_count_fails(self):
        # All 3 readings resolve and verify cleanly at freeze time; one is
        # then deleted from its source table (e.g. a later data-correction
        # pass) -- the manifest's claimed reading count (3) now exceeds what
        # actually resolves (2) on re-verification.
        response = self.make_revision([self.sensor_window(citations=self.sensor_citations(self.readings))])
        self.assertEqual(get_evidence_integrity_status(self.session, response.action_revision_id), "VERIFIED")
        self.session.delete(self.readings[1])
        self.session.commit()
        result = verify_manifest(self.session, response.action_revision_id)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "sensor_reading_unresolved")

    def test_sensor_valid_complete_window_verifies(self):
        response = self.make_revision([self.sensor_window(citations=self.sensor_citations(self.readings))])
        result = verify_manifest(self.session, response.action_revision_id)
        self.assertTrue(result["valid"])
        self.assertEqual(get_evidence_integrity_status(self.session, response.action_revision_id), "VERIFIED")

    def test_approved_revision_missing_document_provenance_release_denied(self):
        response = self.make_revision([self.document_chunk_raw(document_version_id="")])
        self.approve(response.action_revision_id)
        with self.assertRaises(EvidenceIntegrityFailure):
            release_advisory(self.session, response.action_revision_id, actor=self.reviewer)

    def test_approved_revision_unresolved_sensor_reading_release_denied(self):
        response = self.make_revision([self.sensor_window(citations=[self.fake_citation()])])
        self.approve(response.action_revision_id)
        with self.assertRaises(EvidenceIntegrityFailure):
            release_advisory(self.session, response.action_revision_id, actor=self.reviewer)

    # -- BOUNDARY -----------------------------------------------------------

    def test_no_plant_control_capability_introduced(self):
        before = {tool.name for tool in list_tools()}
        response = self.make_revision([self.document_chunk()])
        self.approve(response.action_revision_id)
        release_advisory(self.session, response.action_revision_id, actor=self.reviewer)
        after = {tool.name for tool in list_tools()}
        self.assertEqual(before, after)
        self.assertEqual(after, {"retrieve_documents", "get_pid_regions", "get_maintenance_history",
                                 "get_work_order", "get_latest_reading", "get_sensor_readings",
                                 "compute_sensor_features", "analyze_sensor_maintenance"})


class EvidenceIntegrityHTTPTests(unittest.TestCase):
    """Real HTTP-layer checks: release-denial audit logging and API exposure."""

    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine, tables=TABLES)
        self.session = Session(self.engine)
        self.session.execute(text(
            "CREATE TABLE document_versions (id TEXT PRIMARY KEY, created_at TEXT, document_id TEXT, "
            "source_sha256 TEXT UNIQUE, status TEXT, chunk_count INTEGER, ingestion_metadata TEXT, warnings TEXT)"
        ))
        app.dependency_overrides[get_db] = lambda: self.session
        self.addCleanup(app.dependency_overrides.pop, get_db)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)

        self.requester = User(username="httpd-requester", role="requester", password_hash=hash_password("r"))
        self.reviewer = User(username="httpd-reviewer", role="reviewer", password_hash=hash_password("v"))
        self.session.add_all([self.requester, self.reviewer])
        self.session.commit()

        document = Document(filename="manual.pdf", document_type="manual", source_path="s3://manual.pdf",
                           classification="internal")
        self.session.add(document)
        self.session.commit()
        self.document_version = DocumentVersion(document_id=document.id, source_sha256="a" * 64,
                                                status="processed", chunk_count=1, ingestion_metadata={})
        self.session.add(self.document_version)
        self.session.commit()
        self.document = document
        self.client = TestClient(app)

    def login(self, username, password):
        response = self.client.post("/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)

    def document_chunk(self):
        return _dump(document_chunk_evidence(
            chunk_id="chunk-1", document_id=str(self.document.id), document_version_id=str(self.document_version.id),
            source_filename="manual.pdf", source_sha256=self.document_version.source_sha256,
            section_path=["1"], page_start=1, page_end=1, bounding_boxes=[], quote="original text",
        ))

    def make_revision(self):
        request = QueryRequest(query="Review pump recommendation", request_id=uuid4())
        return govern_response(self.session, request, _state([self.document_chunk()]),
                              requester_user_id=self.requester.id)

    def test_integrity_failure_denies_release_and_is_audited_via_http(self):
        response = self.make_revision()
        self.login("httpd-reviewer", "v")
        decide = self.client.post(f"/approvals/{response.action_revision_id}/decision", json={"decision": "approve"})
        self.assertEqual(decide.status_code, 200, decide.text)

        item = self.session.query(EvidenceManifestItem).join(EvidenceManifest).filter(
            EvidenceManifest.action_revision_id == response.action_revision_id).one()
        self.session.execute(EvidenceManifestItem.__table__.update().where(EvidenceManifestItem.id == item.id)
                            .values(content_hash="0" * 64).execution_options(synchronize_session=False))
        self.session.commit()

        release = self.client.get(f"/approvals/{response.action_revision_id}/release")
        self.assertEqual(release.status_code, 403)

        rows = self.client.get("/audit/log").json()
        failure_rows = [row for row in rows if row["event_type"] == "EVIDENCE_INTEGRITY_FAILED"]
        self.assertEqual(len(failure_rows), 1)
        self.assertEqual(failure_rows[0]["action_revision_id"], str(response.action_revision_id))

    def test_revision_detail_exposes_evidence_integrity_summary(self):
        response = self.make_revision()
        self.login("httpd-reviewer", "v")
        detail = self.client.get(f"/approvals/{response.action_revision_id}").json()
        self.assertEqual(detail["evidence_binding_status"], "VERIFIED")
        self.assertIsNotNone(detail["evidence_manifest_id"])
        self.assertIsNotNone(detail["evidence_manifest_hash"])
        self.assertEqual(len(detail["evidence_item_summaries"]), 1)
        summary = detail["evidence_item_summaries"][0]
        self.assertEqual(summary["evidence_type"], "document_chunk")
        self.assertIn("canonical_item_hash", summary)
        # No raw content leaks through the summary -- only identifiers/hashes.
        self.assertNotIn("quote", summary)


if __name__ == "__main__":
    unittest.main()
