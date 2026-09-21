"""Opt-in real PostgreSQL Phase 5D evidence-manifest immutability/live-source
re-verification checks in an isolated schema. Run with WORKBENCH_TEST_POSTGRES=1.

No SQLite raw-SQL-trigger or real-JSONB-DocumentVersion claims here either --
this is the Phase 5D counterpart to test_phase5c_postgres.py, same isolation
technique."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.agents.evidence import document_chunk_evidence, sensor_window_evidence
from app.core.config import settings
from app.core.security import hash_password
from app.db.models import Document, DocumentVersion, Equipment, EvidenceManifest, EvidenceManifestItem, User
from app.schemas.query import QueryRequest
from app.services.approval import apply_decision, release_advisory
from app.services.evidence_integrity import get_evidence_integrity_status, verify_manifest
from app.services.governance import EvidenceIntegrityFailure, govern_response


def _state(evidence):
    return {"run_id": str(uuid4()), "query": "Review pump operating recommendation", "route": "safety",
            "agent_result": {"schema": "S7", "output": {"summary": "Proposal"}},
            "human_approval_required": False, "evidence": evidence, "warnings": [], "step_records": []}


@unittest.skipUnless(os.environ.get("WORKBENCH_TEST_POSTGRES") == "1", "Real PostgreSQL integration not enabled")
class PostgreSQLEvidenceIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_phase5d_" + uuid4().hex
        cls.admin = create_engine(settings.database_url, connect_args={"connect_timeout": 5})
        with cls.admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.addClassCleanup(cls.cleanup_schema)
        url = make_url(settings.database_url).update_query_dict({"options": f"-csearch_path={cls.schema}"})
        cls.url = url.render_as_string(hide_password=False)
        cls.engine = create_engine(url, connect_args={"connect_timeout": 5})
        cls.addClassCleanup(cls.engine.dispose)
        cls.config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with patch.object(settings, "database_url", cls.url):
            command.upgrade(cls.config, "head")
            command.check(cls.config)

        with Session(cls.engine) as session:
            cls.requester = User(username="pg_d_requester", role="requester", password_hash=hash_password("r"))
            cls.reviewer = User(username="pg_d_reviewer", role="reviewer", password_hash=hash_password("v"))
            cls.equipment = Equipment(equipment_tag="P-101A", name="Pump P-101A", equipment_type="pump")
            session.add_all([cls.requester, cls.reviewer, cls.equipment])
            session.commit()
            cls.document = Document(filename="manual.pdf", document_type="manual", source_path="s3://manual.pdf",
                                    classification="internal")
            session.add(cls.document)
            session.commit()
            cls.document_version = DocumentVersion(document_id=cls.document.id, source_sha256="a" * 64,
                                                   status="processed", chunk_count=1, ingestion_metadata={})
            session.add(cls.document_version)
            session.commit()
            (cls.requester_id, cls.reviewer_id, cls.document_id,
             cls.document_version_id) = (cls.requester.id, cls.reviewer.id, cls.document.id, cls.document_version.id)

    @classmethod
    def cleanup_schema(cls):
        assert cls.schema.startswith("test_phase5d_") and len(cls.schema) == 45
        with cls.admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))
        cls.admin.dispose()

    def document_chunk(self, quote="original text"):
        ref = document_chunk_evidence(
            chunk_id="chunk-1", document_id=str(self.document_id), document_version_id=str(self.document_version_id),
            source_filename="manual.pdf", source_sha256="a" * 64, section_path=["1"], page_start=1, page_end=1,
            bounding_boxes=[], quote=quote,
        )
        return ref.model_dump(mode="json")

    def make_revision(self, quote="original text"):
        with Session(self.engine) as session:
            request = QueryRequest(query="Review pump recommendation", request_id=uuid4())
            response = govern_response(session, request, _state([self.document_chunk(quote)]),
                                       requester_user_id=self.requester_id)
            return response.action_revision_id

    def document_chunk_missing_provenance(self):
        """Astra finding 1: document_version_id empty from the moment the
        EvidenceRef is created -- self-consistent at freeze, only live
        re-verification catches it."""
        ref = document_chunk_evidence(
            chunk_id="chunk-1", document_id=str(self.document_id), document_version_id="",
            source_filename="manual.pdf", source_sha256="a" * 64, section_path=["1"], page_start=1, page_end=1,
            bounding_boxes=[], quote="text",
        )
        return ref.model_dump(mode="json")

    def sensor_window_unresolved(self):
        """Astra finding 2: a citation that never resolves to any real
        SensorReading -- present from the moment the EvidenceRef is created."""
        fake_citation = {"source_filename": "sensors.csv", "source_sha256": "9" * 64, "source_row_number": 999}
        ref = sensor_window_evidence(source_filename="sensors.csv", source_sha256=fake_citation["source_sha256"],
                                     citation_label="fake window", provenance=[fake_citation])
        return ref.model_dump(mode="json")

    # -- IMMUTABILITY (real trigger, not the ORM/SQLAlchemy event guard) ----

    def test_raw_sql_update_of_manifest_denied(self):
        revision_id = self.make_revision()
        with Session(self.engine) as session:
            manifest_id = session.query(EvidenceManifest).filter_by(action_revision_id=revision_id).one().id
        with self.assertRaises(DBAPIError), self.engine.begin() as connection:
            connection.execute(text("UPDATE evidence_manifests SET item_count = 999 WHERE id = :id"),
                              {"id": manifest_id})

    def test_raw_sql_delete_of_manifest_item_denied(self):
        revision_id = self.make_revision()
        with Session(self.engine) as session:
            manifest_id = session.query(EvidenceManifest).filter_by(action_revision_id=revision_id).one().id
            item_id = session.query(EvidenceManifestItem).filter_by(manifest_id=manifest_id).one().id
        with self.assertRaises(DBAPIError), self.engine.begin() as connection:
            connection.execute(text("DELETE FROM evidence_manifest_items WHERE id = :id"), {"id": item_id})

    # -- LIVE RE-VERIFICATION against a real DocumentVersion -----------------

    def test_document_version_source_change_detected_live(self):
        revision_id = self.make_revision()
        with Session(self.engine) as session:
            self.assertEqual(get_evidence_integrity_status(session, revision_id), "VERIFIED")

        # The document was re-ingested under the SAME document_version row
        # with DIFFERENT content (its source_sha256 changed) -- this must be
        # detected live, even though the manifest item itself was never
        # touched.
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE document_versions SET source_sha256 = :new WHERE id = :id"),
                              {"new": "f" * 64, "id": str(self.document_version_id)})

        with Session(self.engine) as session:
            result = verify_manifest(session, revision_id)
            self.assertFalse(result["valid"])
            # Astra repair: renamed from the generic "source_content_changed"
            # to "document_source_hash_mismatch" for document_chunk/pid_region.
            self.assertEqual(result["error_type"], "document_source_hash_mismatch")
            self.assertEqual(get_evidence_integrity_status(session, revision_id), "FAILED")

        # Restore for other tests sharing the class-scoped document_version row.
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE document_versions SET source_sha256 = :orig WHERE id = :id"),
                              {"orig": "a" * 64, "id": str(self.document_version_id)})

    def test_approved_revision_denies_release_after_live_source_drift(self):
        revision_id = self.make_revision()
        with Session(self.engine) as session:
            reviewer = session.get(User, self.reviewer_id)
            apply_decision(session, revision_id=revision_id, reviewer=reviewer, decision="approve")
            session.commit()

        with self.engine.begin() as connection:
            connection.execute(text("UPDATE document_versions SET source_sha256 = :new WHERE id = :id"),
                              {"new": "e" * 64, "id": str(self.document_version_id)})

        with Session(self.engine) as session:
            reviewer = session.get(User, self.reviewer_id)
            with self.assertRaises(EvidenceIntegrityFailure):
                release_advisory(session, revision_id, actor=reviewer)

        with self.engine.begin() as connection:
            connection.execute(text("UPDATE document_versions SET source_sha256 = :orig WHERE id = :id"),
                              {"orig": "a" * 64, "id": str(self.document_version_id)})

    # -- ASTRA REPAIR REGRESSIONS, live against real PostgreSQL --------------

    def test_document_evidence_missing_provenance_fails_and_denies_release_live(self):
        with Session(self.engine) as session:
            request = QueryRequest(query="Review pump recommendation", request_id=uuid4())
            response = govern_response(session, request, _state([self.document_chunk_missing_provenance()]),
                                       requester_user_id=self.requester_id)
            revision_id = response.action_revision_id

        with Session(self.engine) as session:
            result = verify_manifest(session, revision_id)
            self.assertFalse(result["valid"])
            self.assertEqual(result["error_type"], "document_provenance_missing")

        with Session(self.engine) as session:
            reviewer = session.get(User, self.reviewer_id)
            apply_decision(session, revision_id=revision_id, reviewer=reviewer, decision="approve")
            session.commit()

        with Session(self.engine) as session:
            reviewer = session.get(User, self.reviewer_id)
            with self.assertRaises(EvidenceIntegrityFailure):
                release_advisory(session, revision_id, actor=reviewer)

    def test_sensor_evidence_unresolved_reading_fails_and_denies_release_live(self):
        with Session(self.engine) as session:
            request = QueryRequest(query="Review pump recommendation", request_id=uuid4())
            response = govern_response(session, request, _state([self.sensor_window_unresolved()]),
                                       requester_user_id=self.requester_id)
            revision_id = response.action_revision_id

        with Session(self.engine) as session:
            result = verify_manifest(session, revision_id)
            self.assertFalse(result["valid"])
            self.assertEqual(result["error_type"], "sensor_reading_unresolved")

        with Session(self.engine) as session:
            reviewer = session.get(User, self.reviewer_id)
            apply_decision(session, revision_id=revision_id, reviewer=reviewer, decision="approve")
            session.commit()

        with Session(self.engine) as session:
            reviewer = session.get(User, self.reviewer_id)
            with self.assertRaises(EvidenceIntegrityFailure):
                release_advisory(session, revision_id, actor=reviewer)

    def test_migration_downgrade_upgrade_and_metadata(self):
        # Earlier tests in this shared schema already created audit_events
        # rows using the Phase 5D event types (EVIDENCE_MANIFEST_CREATED,
        # etc.) via make_revision(); downgrading narrows the event_type CHECK
        # constraint back to the pre-5D set, which those rows would
        # genuinely violate (correct database behavior, not a migration
        # bug). audit_events is itself immutable (DELETE is trigger-blocked,
        # same as UPDATE) -- TRUNCATE bypasses row-level triggers in
        # PostgreSQL, so it's the only way to clear it here. This test
        # proves the migration's DDL mechanics, not audit content.
        with self.engine.begin() as connection:
            connection.execute(text("TRUNCATE TABLE audit_events"))
        with patch.object(settings, "database_url", self.url):
            command.downgrade(self.config, "0007_phase5c_audit_chain")
            command.upgrade(self.config, "head")
            command.check(self.config)


if __name__ == "__main__":
    unittest.main()
