"""Focused 5A boundary checks. SQLite verifies logic, NOT PostgreSQL concurrency."""
import io
import json
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.agents.graph import _traced
from app.agents.registry import list_tools
from app.agents.state import _or_bool
from app.core.config import settings
from app.db.base import Base
from app.db.models import (
    ActionRevision, Agent, AgentAction, AgentRun, AgentRunStep, ApprovalDecision, AuditChainHead,
    AuditEvent, AuthSession, EvidenceManifest, EvidenceManifestItem, GovernanceRequest, User,
)
from app.db.session import get_db
from app.main import app
from app.schemas.query import QueryRequest
from app.services.canonicalization import canonical_hash, canonical_json
from app.services.governance import (
    GovernanceConflict, ReleaseNotAllowed, assert_release_allowed, create_revision,
    evaluate_governance, get_governance_state, govern_response, replay_request,
)

TABLES = [model.__table__ for model in (
    User, Agent, AgentAction, AgentRun, AgentRunStep, GovernanceRequest, ActionRevision,
    AuthSession, ApprovalDecision, AuditChainHead, AuditEvent, EvidenceManifest, EvidenceManifestItem,
)]


def state(schema="S7", **output):
    return {"run_id": str(uuid4()), "query": "Review pump operating recommendation", "route": "safety",
            "agent_result": {"schema": schema, "output": output or {
                "summary": "Proposal", "proposed_actions": [{"action": "Increase pump speed",
                "action_class": "informational", "approval_status": "approved"}]}},
            "human_approval_required": False, "evidence": [], "warnings": [], "step_records": []}


class CanonicalizationTests(unittest.TestCase):
    def test_fixed_vectors(self):
        vectors = [({}, 'e0f6956d8f60922c997a8df994edcc0527d6dc89fcf79b99c77cfc339142c776'),
                   ({"b": 1.0, "a": "caf\u00e9"}, '40445f606f4a2886605bec31c892ead722b052a34c7bed561cf10ff25e1f24f1'),
                   ({"at": datetime(2026, 9, 20, tzinfo=timezone.utc), "value": -0.0},
                    'c2223524656a2904b8ee05a3644b90916c6ef744b9938915c1d4ffe14ec67142')]
        for payload, expected in vectors:
            self.assertEqual(canonical_hash(payload), expected)

    def test_semantic_key_numeric_and_timestamp_equivalence(self):
        a = {"b": 1.0, "a": datetime(2026, 9, 20, tzinfo=timezone.utc)}
        b = {"a": datetime(2026, 9, 20, 5, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))), "b": 1}
        self.assertEqual(canonical_hash(a), canonical_hash(b))
        self.assertEqual(canonical_hash(a), canonical_hash(json.loads(canonical_json(a))["payload"]))

    def test_utf8_and_material_content(self):
        self.assertIn('caf\u00e9', canonical_json({"text": "caf\u00e9"}))
        self.assertNotEqual(canonical_hash({"speed": 10}), canonical_hash({"speed": 11}))
        self.assertNotEqual(canonical_hash({"query": "a"}), canonical_hash({"query": "b"}))

    def test_unsupported_values_are_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf"), {1: "key"}, {1, 2}, datetime.now(), object(), "\ud800"):
            with self.subTest(type=type(value)), self.assertRaises(ValueError):
                canonical_hash(value)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.request = QueryRequest(query="What was measured?")

    def test_model_approved_and_informational_label_cannot_authorize(self):
        candidate = state(approved=True, approval_status="approved", action_class="informational",
                          proposed_actions=[{"action": "Increase pump speed"}])
        self.assertEqual(evaluate_governance(self.request, candidate), "PENDING_REVIEW")

    def test_specialist_true_creates_requirement(self):
        self.assertEqual(evaluate_governance(self.request, state("S1", answer="Readings", human_approval_required=True)), "PENDING_REVIEW")

    def test_earlier_requirement_survives_later_false(self):
        candidate = state("S1", answer="Readings", human_approval_required=False)
        candidate["human_approval_required"] = _or_bool(True, False)
        self.assertEqual(evaluate_governance(self.request, candidate), "PENDING_REVIEW")
        update = _traced("test", lambda _: {"agent_result": {"output": {"human_approval_required": True}}})({})
        self.assertTrue(update["human_approval_required"])

    def test_schema_and_route_labels_do_not_hide_operational_text(self):
        candidate = state("S1", answer="Increase pump speed", action_class="informational")
        candidate["route"] = "knowledge"
        self.assertEqual(evaluate_governance(self.request, candidate), "PENDING_REVIEW")

    def test_assessments_and_unknown_shapes_fail_conservatively(self):
        for schema in ("S4", "S6", "unknown"):
            self.assertEqual(evaluate_governance(self.request, state(schema, observations=["Reading 4"])), "PENDING_REVIEW")

    def test_informational_does_not_create_actionable_approval(self):
        for schema, output in (("S1", {"answer": "Temperature was 20 C"}), ("S3", {"tags": []}),
                               ("S5", {"reason": "Insufficient evidence"})):
            self.assertEqual(evaluate_governance(self.request, state(schema, **output)), "INFORMATIONAL")

    def test_no_plant_control_tools(self):
        self.assertEqual({tool.name for tool in list_tools()}, {
            "retrieve_documents", "get_pid_regions", "get_maintenance_history", "get_work_order",
            "get_latest_reading", "get_sensor_readings", "compute_sensor_features"})


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine, tables=TABLES)
        self.session = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)
        self.request = QueryRequest(query="Review pump recommendation", request_id=uuid4(), requester_reference="claimed-operator")

    def make_revision(self, candidate=None):
        revision = create_revision(self.session, self.request, candidate or state())
        self.session.commit()
        return revision

    def test_server_owned_state_and_unverified_bindings(self):
        revision = self.make_revision()
        binding = self.session.get(GovernanceRequest, revision.request_id)
        self.assertEqual(revision.governance_status, "PENDING_REVIEW")
        self.assertEqual(binding.identity_status, "UNVERIFIED")
        self.assertEqual(revision.evidence_binding_status, "PENDING_INTEGRITY")
        self.assertEqual(revision.canonical_request_hash, binding.canonical_request_hash)
        self.assertIsNotNone(self.session.get(AgentRun, revision.originating_run_id))

    def test_duplicate_persistence_is_idempotent(self):
        candidate = state()
        first = self.make_revision(candidate)
        retry = deepcopy(candidate); retry["run_id"] = str(uuid4())
        second = self.make_revision(retry)
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(ActionRevision)), 1)

    def test_edit_creates_revision_with_fresh_pending_state(self):
        first = self.make_revision()
        second = self.make_revision(state(summary="Changed proposal", approved=True))
        self.assertNotEqual(first.id, second.id)
        self.assertNotEqual(first.canonical_proposal_hash, second.canonical_proposal_hash)
        self.assertEqual(first.action_id, second.action_id)
        self.assertEqual(second.governance_status, "PENDING_REVIEW")
        self.assertEqual(replay_request(self.session, self.request).action_revision_id, first.id)

    def test_changed_request_or_claim_conflicts(self):
        self.make_revision()
        for changes in ({"query": "Different request"}, {"requester_reference": "another claim"}, {"access_scope": "private"}):
            with self.assertRaises(GovernanceConflict):
                replay_request(self.session, self.request.model_copy(update=changes))

    def test_revision_and_request_orm_immutability(self):
        revision = self.make_revision()
        revision.policy_version = "changed"
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.session.flush()
        self.session.rollback()
        binding = self.session.get(GovernanceRequest, self.request.request_id)
        self.session.delete(binding)
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.session.flush()
        self.session.rollback()

    def test_database_rejects_approved_and_duplicate_revision_identity(self):
        revision = self.make_revision()
        values = {column.name: getattr(revision, column.name) for column in ActionRevision.__table__.columns}
        for changes in ({"id": uuid4()}, {"id": uuid4(), "canonical_proposal_hash": "0" * 64, "governance_status": "APPROVED"}):
            with self.assertRaises(IntegrityError):
                self.session.execute(insert(ActionRevision).values(**(values | changes)))
            self.session.rollback()

    def test_pending_and_unknown_revisions_cannot_release(self):
        revision = self.make_revision()
        for revision_id in (revision.id, uuid4()):
            with self.assertRaises(ReleaseNotAllowed):
                assert_release_allowed(self.session, revision_id)

    def test_direct_invocation_cannot_set_state_or_approver(self):
        with self.assertRaises(TypeError):
            create_revision(self.session, self.request, state(), governance_status="APPROVED", reviewed_by=uuid4())
        self.assertEqual(get_governance_state(self.session, self.make_revision().id), "PENDING_REVIEW")

    def test_legacy_approval_is_not_an_authority(self):
        # Existing Phase 2 rows/IDs have no route into this service's authority lookup.
        from app.db.models import Approval
        legacy = Approval(id=uuid4(), action_id=uuid4(), status="approved", requested_by=uuid4(), reviewed_by=uuid4())
        with self.assertRaises(ReleaseNotAllowed):
            assert_release_allowed(self.session, legacy.id)
        revision = self.make_revision(state(approved=True, operator_approved=True))
        with self.assertRaises(ReleaseNotAllowed):
            assert_release_allowed(self.session, revision.id)

    def test_trace_disable_cannot_remove_required_run_provenance(self):
        with patch.object(settings, "agent_trace_enabled", False):
            revision = self.make_revision()
        run = self.session.get(AgentRun, revision.originating_run_id)
        self.assertIsNotNone(run)
        self.assertIsNone(run.query_text)

    def test_existing_requirement_cannot_be_downgraded_by_changed_output(self):
        self.make_revision()
        second = self.make_revision(state("S1", answer="Just a reading", human_approval_required=False))
        self.assertEqual(second.governance_status, "PENDING_REVIEW")

    def test_nested_specialist_requirement_persists_pending(self):
        response = govern_response(self.session, self.request, state("S1", answer="Reading 20 C", human_approval_required=True))
        self.assertEqual(response.governance_status, "PENDING_REVIEW")
        self.assertIsNotNone(self.session.get(ActionRevision, response.action_revision_id))

    def test_evidence_snapshot_bound_to_proposal_hash(self):
        candidate = state()
        first = self.make_revision(candidate)
        candidate["evidence"] = [{"kind": "document_chunk", "evidence_id": "new-source", "source_sha256": "a" * 64,
                                  "source_filename": "f.pdf", "locator": "page 1", "quote": "new evidence text"}]
        second = self.make_revision(candidate)
        self.assertNotEqual(first.canonical_proposal_hash, second.canonical_proposal_hash)
        self.assertIn("new-source", second.canonical_proposal)

    def test_response_is_a_draft_without_model_authority(self):
        candidate = state(approved=True, authorization="granted", human_approval_required=False,
                          proposed_actions=[{"action": "Adjust speed", "approval_status": "approved"}])
        response = govern_response(self.session, self.request, candidate)
        self.assertEqual(response.governance_status, "PENDING_REVIEW")
        self.assertEqual(response.presentation, "DRAFT")
        self.assertTrue(response.human_review_required)
        self.assertNotIn('"approved"', json.dumps(response.agent_result))
        self.assertNotIn("approval_status", json.dumps(response.agent_result))

    def test_informational_response_has_no_revision_or_action(self):
        response = govern_response(self.session, QueryRequest(query="What was measured?"), state("S1", answer="Reading 20 C"))
        self.assertEqual(response.governance_status, "INFORMATIONAL")
        self.assertIsNone(response.action_revision_id)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(AgentAction)), 0)

    def test_query_integration_replay_and_conflict(self):
        app.dependency_overrides[get_db] = lambda: self.session
        self.addCleanup(app.dependency_overrides.pop, get_db)
        with TestClient(app) as client, patch("app.api.routes.query.run_graph", return_value=state()) as graph:
            body = self.request.model_dump(mode="json")
            first = client.post("/query", json=body)
            self.assertEqual(first.status_code, 200, first.text)
            second = client.post("/query", json=body)
            self.assertEqual(first.json(), second.json())
            graph.assert_called_once()
            conflict = client.post("/query", json=body | {"query": "different"})
            self.assertEqual(conflict.status_code, 409)

    def test_client_authority_fields_are_rejected(self):
        with TestClient(app) as client:
            for field in ("approved", "approval_status", "approval_required", "human_approval_required", "authorized",
                          "authorization", "action_class", "safe_to_proceed", "permission_granted", "operator_approved"):
                response = client.post("/query", json={"query": "review", field: True})
                self.assertEqual(response.status_code, 422, field)
            self.assertEqual(client.post(f"/approvals/{uuid4()}", json={"approved": True}).json()["status"], "not_implemented")
            # Phase 5B: this endpoint is now real and requires authentication;
            # an unauthenticated caller is rejected before any body/authority
            # field is even considered. See test_phase5b.py for the full
            # authenticated decision-endpoint contract.
            self.assertEqual(client.post(f"/approvals/{uuid4()}/decision", json={"approved": True}).status_code, 401)

    def test_commit_failure_does_not_return_draft(self):
        with patch.object(self.session, "commit", side_effect=RuntimeError("commit failed")):
            with self.assertRaises(RuntimeError):
                govern_response(self.session, self.request, state())
        self.assertEqual(self.session.scalar(select(func.count()).select_from(ActionRevision)), 0)


class MigrationTests(unittest.TestCase):
    def test_offline_migration_contains_database_boundary(self):
        output = io.StringIO()
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"), output_buffer=output)
        command.upgrade(config, "head", sql=True)
        sql = output.getvalue()
        for required in ("CREATE TABLE action_revisions", "BEFORE UPDATE OR DELETE", "DEFERRABLE INITIALLY DEFERRED",
                         "governance_status = 'PENDING_REVIEW'", "sha256(convert_to", "uq_action_revision_content"):
            self.assertIn(required, sql)
        output.truncate(0)
        output.seek(0)
        command.downgrade(config, "0005_governance_revisions:0004_agent_runs", sql=True)
        self.assertIn("DROP TABLE action_revisions", output.getvalue())
        self.assertNotIn("DROP TABLE approvals", output.getvalue())


if __name__ == "__main__":
    unittest.main()
