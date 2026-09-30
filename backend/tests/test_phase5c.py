"""Phase 5C tamper-evident audit chain checks. SQLite verifies deterministic
hashing/chain logic and ORM-level immutability, NOT PostgreSQL raw-SQL
immutability or concurrency -- see test_phase5c_postgres.py for those."""
import hashlib
import json
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, insert
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.agents.registry import list_tools
from app.core.security import hash_password
from app.db.base import Base
from app.db.models import AuthIdentity, AuthChallenge, ResetCapability, AuthAttempt, OIDCFlow
from app.db.models import (
    ActionRevision, Agent, AgentAction, AgentRun, AgentRunStep, ApprovalDecision, AuditChainHead,
    AuditCheckpoint, AuditEvent, AuditLog, AuthSession, EvidenceManifest, EvidenceManifestItem,
    GovernanceRequest, User,
)
# app.db.models.AuditLog (Phase 2) is intentionally NOT in TABLES below: its
# event_data column is a raw postgresql.JSONB (not the SQLite-compatible
# JSON().with_variant pattern the Phase 5C tables use), so it cannot be
# created against SQLite -- it never was exercised by any SQLite test before
# Phase 5C either. See test_phase5c_postgres.py for a real legacy-row check
# against actual PostgreSQL JSONB.
from app.db.session import get_db
from app.main import app
from app.schemas.query import QueryRequest
from app.services.approval import apply_decision, release_advisory
from app.services.audit import (
    CHAIN_ID, SCHEMA_VERSION, _envelope, _genesis_previous_hash, append_event, create_checkpoint, verify_chain,
)
from app.services.canonicalization import canonical_hash, canonical_json
from app.services.governance import govern_response
from test_phase5a import state

TABLES = [model.__table__ for model in (
    AuthIdentity, AuthChallenge, ResetCapability, AuthAttempt, OIDCFlow,
    User, Agent, AgentAction, AgentRun, AgentRunStep, GovernanceRequest, ActionRevision,
    AuthSession, ApprovalDecision, AuditChainHead, AuditEvent, AuditCheckpoint,
    EvidenceManifest, EvidenceManifestItem,
)]


def _forge_event(session, *, sequence_number, previous_hash, chain_id=CHAIN_ID, payload=None,
                 event_type="LOGIN_SUCCESS", actor_id=None, actor_kind="system"):
    """Directly insert an AuditEvent row, bypassing append_event -- the only
    way to construct a deliberately-tampered/forged row, since a genuine
    append_event call always produces an internally-consistent one."""
    payload = payload if payload is not None else {"note": "forged"}
    canonical_payload_hash = canonical_hash(payload)
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    envelope = _envelope(
        schema_version=SCHEMA_VERSION, chain_id=chain_id, sequence_number=sequence_number, event_id=event_id,
        occurred_at=occurred_at, actor_id=actor_id, actor_kind=actor_kind, event_type=event_type,
        request_id=None, action_revision_id=None, decision_id=None,
        canonical_payload_hash=canonical_payload_hash, previous_hash=previous_hash,
    )
    canonical_event_json = canonical_json(envelope)
    event_hash = hashlib.sha256(canonical_event_json.encode("utf-8")).hexdigest()
    session.execute(insert(AuditEvent).values(
        id=event_id, schema_version=SCHEMA_VERSION, chain_id=chain_id, sequence_number=sequence_number,
        occurred_at=occurred_at, actor_id=actor_id, actor_kind=actor_kind, event_type=event_type,
        request_id=None, action_revision_id=None, decision_id=None, payload=payload,
        canonical_payload_hash=canonical_payload_hash, previous_hash=previous_hash,
        canonical_event_json=canonical_event_json, event_hash=event_hash,
    ))
    session.commit()
    return event_hash


class AuditChainTests(unittest.TestCase):
    """Direct service-level checks (no HTTP layer)."""

    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine, tables=TABLES)
        self.session = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)

        self.requester = User(username="c-requester", role="requester", password_hash=hash_password("r"))
        self.reviewer = User(username="c-reviewer", role="reviewer", password_hash=hash_password("v"))
        self.session.add_all([self.requester, self.reviewer])
        self.session.commit()

    # -- HASHING / CHAIN ---------------------------------------------------

    def test_deterministic_identical_event_same_hash(self):
        # event_hash is exactly sha256(canonical_event_json) -- recomputing
        # it independently from the row's own stored text always agrees.
        record = append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id,
                             actor_kind="user", payload={"username": "x"})
        self.session.commit()
        self.assertEqual(hashlib.sha256(record.canonical_event_json.encode()).hexdigest(), record.event_hash)
        # Two separately-appended events with the SAME inputs otherwise, on
        # DIFFERENT chains, deterministically produce DIFFERENT hashes purely
        # because chain_id is bound into the hash (not from randomness).
        other = append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id,
                            actor_kind="user", payload={"username": "x"}, chain_id="deterministic-test-chain")
        self.session.commit()
        self.assertNotEqual(record.event_hash, other.event_hash)

    def test_fixed_genesis_vector(self):
        # Fixed deterministic test vector (docs/phase5c.md, "Genesis design"):
        # pinned so a future change to canonicalization or the genesis
        # representation is caught here, never silently.
        self.assertEqual(
            _genesis_previous_hash("workbench-governance-v1"),
            "1267453af39caf7b4393cf67e01841fc28736d25e78e82abcfd70e60321a9dbe",
        )

    def test_payload_modification_detected(self):
        append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id, actor_kind="user",
                    payload={"username": "original"})
        self.session.commit()
        row = self.session.query(AuditEvent).one()
        self.session.execute(AuditEvent.__table__.update().where(AuditEvent.id == row.id)
                            .values(payload={"username": "tampered"}).execution_options(synchronize_session=False))
        self.session.commit()
        self.session.expire_all()
        result = verify_chain(self.session)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "payload_hash_mismatch")
        self.assertEqual(result["first_error_sequence"], 1)

    def test_metadata_modification_detected(self):
        append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id, actor_kind="user",
                    payload={"username": "x"})
        self.session.commit()
        row = self.session.query(AuditEvent).one()
        self.session.execute(AuditEvent.__table__.update().where(AuditEvent.id == row.id)
                            .values(event_type="LOGIN_FAILURE").execution_options(synchronize_session=False))
        self.session.commit()
        self.session.expire_all()
        result = verify_chain(self.session)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "event_hash_mismatch")

    def test_event_hash_modification_detected(self):
        append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id, actor_kind="user",
                    payload={"username": "x"})
        self.session.commit()
        row = self.session.query(AuditEvent).one()
        self.session.execute(AuditEvent.__table__.update().where(AuditEvent.id == row.id)
                            .values(event_hash="0" * 64).execution_options(synchronize_session=False))
        self.session.commit()
        self.session.expire_all()
        result = verify_chain(self.session)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "event_hash_mismatch")

    def test_previous_hash_modification_detected(self):
        append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id, actor_kind="user",
                    payload={"username": "x"})
        append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id, actor_kind="user",
                    payload={"username": "y"})
        self.session.commit()
        second = self.session.query(AuditEvent).filter_by(sequence_number=2).one()
        self.session.execute(AuditEvent.__table__.update().where(AuditEvent.id == second.id)
                            .values(previous_hash="1" * 64).execution_options(synchronize_session=False))
        self.session.commit()
        self.session.expire_all()
        result = verify_chain(self.session)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "previous_hash_mismatch")
        self.assertEqual(result["first_error_sequence"], 2)

    def test_deleted_middle_event_detected(self):
        for i in range(3):
            append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id, actor_kind="user",
                        payload={"n": i})
        self.session.commit()
        middle = self.session.query(AuditEvent).filter_by(sequence_number=2).one()
        self.session.execute(AuditEvent.__table__.delete().where(AuditEvent.id == middle.id))
        self.session.commit()
        result = verify_chain(self.session)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "sequence_gap")
        self.assertEqual(result["first_error_sequence"], 3)

    def test_inserted_event_detected(self):
        append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id, actor_kind="user",
                    payload={"n": 1})
        self.session.commit()
        head = self.session.query(AuditChainHead).filter_by(chain_id=CHAIN_ID).one()
        # An attacker inserting an extra event must either reuse a sequence
        # number (caught as duplicate_sequence_number, see below) or forge a
        # previous_hash it cannot correctly derive without controlling the
        # legitimate chain head -- simulate that "wrong previous_hash" case.
        _forge_event(self.session, sequence_number=2, previous_hash="f" * 64)
        result = verify_chain(self.session)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "previous_hash_mismatch")
        self.assertEqual(result["first_error_sequence"], 2)
        self.assertEqual(head.next_sequence_number, 2)  # the lock/cursor was never advanced by the forgery

    def test_reordered_event_detected(self):
        # sequence_number is bound into event_hash, so content legitimately
        # computed "as if" it were event #3 but stored at sequence_number=2
        # (a splice/reorder) fails hash verification at sequence 2.
        chain = "reorder-test-chain"
        first = append_event(self.session, chain_id=chain, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id,
                            actor_kind="user", payload={"n": 1})
        self.session.commit()
        payload_b = {"n": "b"}
        hash_b = canonical_hash(payload_b)
        event_id = uuid4()
        occurred_at = datetime.now(timezone.utc)
        envelope_as_3 = _envelope(schema_version=SCHEMA_VERSION, chain_id=chain, sequence_number=3,
                                  event_id=event_id, occurred_at=occurred_at, actor_id=None, actor_kind="system",
                                  event_type="LOGIN_SUCCESS", request_id=None, action_revision_id=None,
                                  decision_id=None, canonical_payload_hash=hash_b, previous_hash=first.event_hash)
        text = canonical_json(envelope_as_3)
        forged_hash = hashlib.sha256(text.encode()).hexdigest()
        self.session.execute(insert(AuditEvent).values(
            id=event_id, schema_version=SCHEMA_VERSION, chain_id=chain, sequence_number=2,
            occurred_at=occurred_at, actor_id=None, actor_kind="system", event_type="LOGIN_SUCCESS",
            request_id=None, action_revision_id=None, decision_id=None, payload=payload_b,
            canonical_payload_hash=hash_b, previous_hash=first.event_hash, canonical_event_json=text,
            event_hash=forged_hash,
        ))
        self.session.commit()
        result = verify_chain(self.session, chain_id=chain)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "event_hash_mismatch")
        self.assertEqual(result["first_error_sequence"], 2)

    def test_sequence_gap_detected(self):
        append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id, actor_kind="user",
                    payload={"n": 1})
        self.session.commit()
        first = self.session.query(AuditEvent).one()
        _forge_event(self.session, sequence_number=5, previous_hash=first.event_hash)
        result = verify_chain(self.session)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "sequence_gap")
        self.assertEqual(result["first_error_sequence"], 5)

    def test_duplicate_sequence_prevented(self):
        append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id, actor_kind="user",
                    payload={"n": 1})
        self.session.commit()
        with self.assertRaises(Exception):
            self.session.execute(insert(AuditEvent).values(
                id=uuid4(), schema_version=SCHEMA_VERSION, chain_id=CHAIN_ID, sequence_number=1,
                occurred_at=datetime.now(timezone.utc), actor_id=None, actor_kind="system",
                event_type="LOGIN_SUCCESS", request_id=None, action_revision_id=None, decision_id=None,
                payload={"n": "dup"}, canonical_payload_hash=canonical_hash({"n": "dup"}),
                previous_hash=_genesis_previous_hash(CHAIN_ID), canonical_event_json="{}",
                event_hash="a" * 64,
            ))
            self.session.commit()
        self.session.rollback()

    def test_wrong_chain_id_detected(self):
        # A row whose STORED chain_id/sequence_number/previous_hash columns
        # fit perfectly as position 1 of CHAIN_ID, but whose event_hash was
        # actually computed with chain_id="other-chain" embedded in the
        # hashed envelope -- a splice that passes every earlier check
        # (sequence, stored chain_id, previous_hash) and is caught only when
        # the hash itself is recomputed from the row's own column values.
        genesis = _genesis_previous_hash(CHAIN_ID)
        payload = {"n": 1}
        payload_hash = canonical_hash(payload)
        event_id = uuid4()
        occurred_at = datetime.now(timezone.utc)
        envelope = _envelope(schema_version=SCHEMA_VERSION, chain_id="other-chain", sequence_number=1,
                            event_id=event_id, occurred_at=occurred_at, actor_id=None, actor_kind="system",
                            event_type="LOGIN_SUCCESS", request_id=None, action_revision_id=None,
                            decision_id=None, canonical_payload_hash=payload_hash, previous_hash=genesis)
        text = canonical_json(envelope)
        forged_hash = hashlib.sha256(text.encode()).hexdigest()
        self.session.execute(insert(AuditEvent).values(
            id=event_id, schema_version=SCHEMA_VERSION, chain_id=CHAIN_ID, sequence_number=1,
            occurred_at=occurred_at, actor_id=None, actor_kind="system", event_type="LOGIN_SUCCESS",
            request_id=None, action_revision_id=None, decision_id=None, payload=payload,
            canonical_payload_hash=payload_hash, previous_hash=genesis, canonical_event_json=text,
            event_hash=forged_hash,
        ))
        self.session.commit()
        result = verify_chain(self.session, chain_id=CHAIN_ID)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error_type"], "wrong_chain_id")

    def test_valid_chain_verifies(self):
        for i in range(4):
            append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id, actor_kind="user",
                        payload={"n": i})
        self.session.commit()
        result = verify_chain(self.session)
        self.assertTrue(result["valid"])
        self.assertEqual(result["events_checked"], 4)
        self.assertEqual(result["first_sequence"], 1)
        self.assertEqual(result["last_sequence"], 4)
        self.assertIsNone(result["first_error_sequence"])
        self.assertIsNone(result["error_type"])

    def test_empty_chain_verifies(self):
        result = verify_chain(self.session, chain_id="never-used-chain")
        self.assertTrue(result["valid"])
        self.assertEqual(result["events_checked"], 0)
        self.assertIsNone(result["first_sequence"])

    # -- IMMUTABILITY (ORM level; PostgreSQL raw-SQL in test_phase5c_postgres.py) --

    def test_orm_update_denied(self):
        record = append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id,
                             actor_kind="user", payload={"n": 1})
        self.session.commit()
        record.event_type = "LOGIN_FAILURE"
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.session.flush()
        self.session.rollback()

    # -- GOVERNANCE INTEGRATION --------------------------------------------

    def make_revision(self):
        request = QueryRequest(query="Review pump recommendation", request_id=uuid4())
        return request, state()

    def test_pending_revision_creation_audited(self):
        request, candidate = self.make_revision()
        response = govern_response(self.session, request, candidate, requester_user_id=self.requester.id)
        result = verify_chain(self.session)
        self.assertTrue(result["valid"])
        # Phase 5D: revision creation now ALSO freezes+audits an evidence
        # manifest in the same transaction -- see test_phase5d.py for the
        # manifest-specific checks; this test only re-confirms the audit
        # chain sees both events, in order, still fully valid.
        self.assertEqual(result["events_checked"], 2)
        rows = self.session.query(AuditEvent).order_by(AuditEvent.sequence_number).all()
        self.assertEqual([row.event_type for row in rows], ["GOVERNED_REVISION_CREATED", "EVIDENCE_MANIFEST_CREATED"])
        row = rows[0]
        self.assertEqual(row.actor_id, self.requester.id)
        self.assertEqual(row.actor_kind, "user")
        self.assertEqual(row.request_id, response.request_id)
        self.assertEqual(row.action_revision_id, response.action_revision_id)

    def test_replay_does_not_double_audit(self):
        request, candidate = self.make_revision()
        govern_response(self.session, request, candidate, requester_user_id=self.requester.id)
        govern_response(self.session, request, candidate, requester_user_id=self.requester.id)  # replay
        self.assertEqual(self.session.query(AuditEvent).count(), 2)

    def test_approve_audited(self):
        request, candidate = self.make_revision()
        response = govern_response(self.session, request, candidate, requester_user_id=self.requester.id)
        decision = apply_decision(self.session, revision_id=response.action_revision_id, reviewer=self.reviewer,
                                  decision="approve")
        self.session.commit()
        rows = self.session.query(AuditEvent).order_by(AuditEvent.sequence_number).all()
        self.assertEqual([row.event_type for row in rows],
                        ["GOVERNED_REVISION_CREATED", "EVIDENCE_MANIFEST_CREATED", "APPROVAL_DECISION_APPROVE"])
        approve_row = rows[2]
        self.assertEqual(approve_row.actor_id, self.reviewer.id)
        self.assertEqual(approve_row.decision_id, decision.id)
        self.assertEqual(approve_row.action_revision_id, response.action_revision_id)
        self.assertTrue(verify_chain(self.session)["valid"])

    def test_reject_audited(self):
        request, candidate = self.make_revision()
        response = govern_response(self.session, request, candidate, requester_user_id=self.requester.id)
        apply_decision(self.session, revision_id=response.action_revision_id, reviewer=self.reviewer,
                      decision="reject")
        self.session.commit()
        event_types = [row.event_type for row in self.session.query(AuditEvent)
                      .order_by(AuditEvent.sequence_number)]
        self.assertIn("APPROVAL_DECISION_REJECT", event_types)

    def test_revoke_audited(self):
        request, candidate = self.make_revision()
        response = govern_response(self.session, request, candidate, requester_user_id=self.requester.id)
        apply_decision(self.session, revision_id=response.action_revision_id, reviewer=self.reviewer,
                      decision="approve")
        self.session.commit()
        apply_decision(self.session, revision_id=response.action_revision_id, reviewer=self.reviewer,
                      decision="revoke")
        self.session.commit()
        event_types = [row.event_type for row in self.session.query(AuditEvent)
                      .order_by(AuditEvent.sequence_number)]
        self.assertEqual(event_types, ["GOVERNED_REVISION_CREATED", "EVIDENCE_MANIFEST_CREATED",
                                       "APPROVAL_DECISION_APPROVE", "APPROVAL_DECISION_REVOKE"])
        self.assertTrue(verify_chain(self.session)["valid"])

    def test_advisory_release_audited(self):
        request, candidate = self.make_revision()
        response = govern_response(self.session, request, candidate, requester_user_id=self.requester.id)
        apply_decision(self.session, revision_id=response.action_revision_id, reviewer=self.reviewer,
                      decision="approve")
        self.session.commit()
        release_advisory(self.session, response.action_revision_id, actor=self.reviewer)
        rows = self.session.query(AuditEvent).order_by(AuditEvent.sequence_number).all()
        # Phase 5D: assert_release_allowed also re-verifies evidence integrity
        # and audits EVIDENCE_INTEGRITY_VERIFIED before release_advisory's own
        # ADVISORY_RELEASE_SUCCESS -- see test_phase5d.py for the dedicated
        # integrity-verification tests.
        self.assertEqual([row.event_type for row in rows],
                        ["GOVERNED_REVISION_CREATED", "EVIDENCE_MANIFEST_CREATED", "APPROVAL_DECISION_APPROVE",
                         "EVIDENCE_INTEGRITY_VERIFIED", "ADVISORY_RELEASE_SUCCESS"])
        self.assertEqual(rows[-1].actor_id, self.reviewer.id)
        self.assertEqual(rows[-1].action_revision_id, response.action_revision_id)
        self.assertTrue(verify_chain(self.session)["valid"])

    def test_checkpoint_records_current_head(self):
        append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id, actor_kind="user",
                    payload={"n": 1})
        self.session.commit()
        checkpoint = create_checkpoint(self.session)
        self.session.commit()
        self.assertIsNotNone(checkpoint)
        head = self.session.query(AuditChainHead).filter_by(chain_id=CHAIN_ID).one()
        self.assertEqual(checkpoint.head_hash, head.head_hash)
        self.assertEqual(checkpoint.sequence_number, 1)

    def test_checkpoint_empty_chain_returns_none(self):
        self.assertIsNone(create_checkpoint(self.session, chain_id="never-used-chain-2"))

    # -- SECURITY ------------------------------------------------------------

    def test_append_event_rejects_client_supplied_hash_fields(self):
        with self.assertRaises(TypeError):
            append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id, actor_kind="user",
                        payload={}, event_hash="a" * 64)
        with self.assertRaises(TypeError):
            append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id, actor_kind="user",
                        payload={}, previous_hash="a" * 64)

    def test_no_secrets_in_audit_payload(self):
        request, candidate = self.make_revision()
        govern_response(self.session, request, candidate, requester_user_id=self.requester.id)
        for row in self.session.query(AuditEvent).all():
            serialized = json.dumps(row.payload)
            self.assertNotIn("password", serialized.lower())
            self.assertNotIn("token", serialized.lower())
            self.assertNotIn("session", serialized.lower())

    # -- LEGACY --------------------------------------------------------------

    def test_legacy_audit_log_is_not_chained_history(self):
        # app.db.models.AuditLog (Phase 2) is a separate table/class from
        # AuditEvent (Phase 5C) with no shared identity -- verify_chain's
        # query targets AuditEvent exclusively, so it is structurally
        # impossible for a legacy row to be counted as chained history. See
        # test_phase5c_postgres.py for a real inserted-legacy-row check
        # (AuditLog's JSONB column needs real PostgreSQL, not SQLite).
        self.assertNotEqual(AuditLog.__tablename__, AuditEvent.__tablename__)
        self.assertFalse(hasattr(AuditLog, "chain_id"))
        self.assertFalse(hasattr(AuditLog, "sequence_number"))
        result = verify_chain(self.session)
        self.assertTrue(result["valid"])
        self.assertEqual(result["events_checked"], 0)

    # -- BOUNDARY -----------------------------------------------------------

    def test_no_plant_control_capability_introduced(self):
        before = {tool.name for tool in list_tools()}
        request, candidate = self.make_revision()
        response = govern_response(self.session, request, candidate, requester_user_id=self.requester.id)
        apply_decision(self.session, revision_id=response.action_revision_id, reviewer=self.reviewer,
                      decision="approve")
        self.session.commit()
        release_advisory(self.session, response.action_revision_id, actor=self.reviewer)
        after = {tool.name for tool in list_tools()}
        self.assertEqual(before, after)
        self.assertEqual(after, {"retrieve_documents", "get_pid_regions", "get_maintenance_history",
                                 "get_work_order", "get_latest_reading", "get_sensor_readings",
                                 "compute_sensor_features", "analyze_sensor_maintenance"})


class AuditHTTPTests(unittest.TestCase):
    """Real HTTP-layer authorization checks for the read-only audit API."""

    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine, tables=TABLES)
        self.session = Session(self.engine)
        app.dependency_overrides[get_db] = lambda: self.session
        self.addCleanup(app.dependency_overrides.pop, get_db)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)

        self.requester = User(username="httpc-requester", role="requester", password_hash=hash_password("r"))
        self.reviewer = User(username="httpc-reviewer", role="reviewer", password_hash=hash_password("v"))
        self.session.add_all([self.requester, self.reviewer])
        self.session.commit()
        self.client = TestClient(app)

    def login(self, username, password):
        response = self.client.post("/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)

    def test_unauthenticated_cannot_read_audit_log_or_verify(self):
        self.assertEqual(self.client.get("/audit/log").status_code, 401)
        self.assertEqual(self.client.get("/audit/verify").status_code, 401)

    def test_requester_role_cannot_read_audit_log_or_verify(self):
        self.login("httpc-requester", "r")
        self.assertEqual(self.client.get("/audit/log").status_code, 403)
        self.assertEqual(self.client.get("/audit/verify").status_code, 403)

    def test_reviewer_can_read_audit_log_and_verify(self):
        self.login("httpc-reviewer", "v")
        log_response = self.client.get("/audit/log")
        self.assertEqual(log_response.status_code, 200)
        # Login itself is a mandatory audited event.
        self.assertTrue(any(row["event_type"] == "LOGIN_SUCCESS" for row in log_response.json()))
        verify_response = self.client.get("/audit/verify")
        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(verify_response.json()["valid"])

    def test_login_failure_is_audited_without_password(self):
        self.client.post("/auth/login", json={"username": "httpc-reviewer", "password": "wrong"})
        self.login("httpc-reviewer", "v")
        rows = self.client.get("/audit/log").json()
        failure_rows = [row for row in rows if row["event_type"] == "LOGIN_FAILURE"]
        self.assertEqual(len(failure_rows), 1)
        self.assertNotIn("wrong", json.dumps(failure_rows[0]["payload"]))

    def test_unauthorized_role_cannot_mutate_audit_via_orm(self):
        # No route accepts audit fields at all (read-only API); the ORM-level
        # immutability guard (test_orm_update_denied above) is the real
        # backstop even for a caller with direct database access.
        self.login("httpc-reviewer", "v")
        record = append_event(self.session, event_type="LOGIN_SUCCESS", actor_id=self.reviewer.id,
                             actor_kind="user", payload={"n": 1})
        self.session.commit()
        record.event_type = "LOGIN_FAILURE"
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.session.flush()
        self.session.rollback()


if __name__ == "__main__":
    unittest.main()
