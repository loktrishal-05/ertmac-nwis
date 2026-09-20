"""Focused 5B authenticated approval-workflow checks. SQLite verifies logic,
NOT PostgreSQL concurrency -- see test_phase5b_postgres.py for that."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, insert
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.agents.registry import list_tools
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db.base import Base
from app.db.models import (
    ActionRevision, Agent, AgentAction, AgentRun, AgentRunStep, ApprovalDecision, AuthSession,
    GovernanceRequest, User,
)
from app.db.session import get_db
from app.main import app
from app.schemas.query import QueryRequest
from app.services.approval import (
    DecisionConflict, DecisionNotAllowed, apply_decision, pending_reviews, release_advisory,
)
from app.services.governance import ReleaseNotAllowed, assert_release_allowed, create_revision, get_governance_state
from test_phase5a import state

TABLES = [model.__table__ for model in (
    User, Agent, AgentAction, AgentRun, AgentRunStep, GovernanceRequest, ActionRevision,
    AuthSession, ApprovalDecision,
)]


class ApprovalServiceTests(unittest.TestCase):
    """Direct service-level checks (no HTTP layer)."""

    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine, tables=TABLES)
        self.session = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)

        self.requester = User(username="requester1", role="requester", password_hash=hash_password("req-pass-1"))
        self.reviewer = User(username="reviewer1", role="reviewer", password_hash=hash_password("rev-pass-1"))
        self.other_reviewer = User(username="reviewer2", role="reviewer", password_hash=hash_password("rev-pass-2"))
        self.admin = User(username="admin1", role="admin", password_hash=hash_password("admin-pass-1"))
        self.session.add_all([self.requester, self.reviewer, self.other_reviewer, self.admin])
        self.session.commit()

    def make_revision(self, *, requester_user_id=None, candidate=None, request_id=None):
        request = QueryRequest(query="Review pump recommendation", request_id=request_id or uuid4())
        revision = create_revision(self.session, request, candidate or state(), requester_user_id=requester_user_id)
        self.session.commit()
        return revision

    # -- AUTHENTICATION -----------------------------------------------

    def test_password_plaintext_never_stored(self):
        raw = "correct-horse-battery-staple"
        hashed = hash_password(raw)
        self.assertNotIn(raw, hashed)
        self.assertTrue(hashed.startswith("$argon2id$"))
        self.assertTrue(verify_password(raw, hashed))
        self.assertFalse(verify_password("wrong-password", hashed))

    # -- AUTHORIZATION --------------------------------------------------

    def test_requester_cannot_approve(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        with self.assertRaises(DecisionNotAllowed):
            apply_decision(self.session, revision_id=revision.id, reviewer=self.requester, decision="approve")

    def test_reviewer_can_access_permitted_pending_review(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        pending = pending_reviews(self.session, viewer=self.reviewer)
        self.assertIn(revision.id, {rev.id for rev in pending})

    def test_self_approval_is_rejected(self):
        revision = self.make_revision(requester_user_id=self.reviewer.id)
        with self.assertRaisesRegex(DecisionNotAllowed, "Self-approval"):
            apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="approve")

    def test_ordinary_requester_cannot_approve_via_direct_service_call(self):
        # Astra finding 1 (HIGH): a DIFFERENT ordinary requester -- not the
        # revision's own requester, so self-approval alone would never catch
        # this -- must still be denied by the SERVICE itself, not only the
        # HTTP require_role dependency, when apply_decision is called directly.
        other_requester = User(username="requester2", role="requester", password_hash=hash_password("req-pass-2"))
        self.session.add(other_requester)
        self.session.commit()
        revision = self.make_revision(requester_user_id=self.requester.id)
        with self.assertRaisesRegex(DecisionNotAllowed, "authorized reviewer"):
            apply_decision(self.session, revision_id=revision.id, reviewer=other_requester, decision="approve")
        self.assertEqual(get_governance_state(self.session, revision.id), "PENDING_REVIEW")

    def test_unverified_requester_fails_closed(self):
        # Section 4: no reliable requester identity -> deny review entirely,
        # not a convenience bypass that assumes it's fine.
        revision = self.make_revision(requester_user_id=None)
        with self.assertRaisesRegex(DecisionNotAllowed, "unverified"):
            apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="approve")

    # -- BINDING ---------------------------------------------------------

    def test_approval_binds_exact_revision_and_hashes(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        decision = apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="approve")
        self.assertEqual(decision.action_revision_id, revision.id)
        self.assertEqual(decision.canonical_request_hash, revision.canonical_request_hash)
        self.assertEqual(decision.canonical_proposal_hash, revision.canonical_proposal_hash)

    def test_wrong_expected_revision_rejected(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        with self.assertRaises(DecisionConflict):
            apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="approve",
                          expected_revision_id=uuid4())

    def test_changed_proposal_requires_new_review(self):
        request_id = uuid4()
        first = self.make_revision(requester_user_id=self.requester.id, request_id=request_id)
        second = self.make_revision(requester_user_id=self.requester.id, request_id=request_id,
                                    candidate=state(summary="Changed proposal"))
        self.assertNotEqual(first.id, second.id)
        apply_decision(self.session, revision_id=first.id, reviewer=self.reviewer, decision="approve")
        self.assertEqual(get_governance_state(self.session, second.id), "PENDING_REVIEW")

    def test_approval_for_revision_a_cannot_release_revision_b(self):
        first = self.make_revision(requester_user_id=self.requester.id)
        second = self.make_revision(requester_user_id=self.requester.id)
        apply_decision(self.session, revision_id=first.id, reviewer=self.reviewer, decision="approve")
        assert_release_allowed(self.session, first.id)
        with self.assertRaises(ReleaseNotAllowed):
            assert_release_allowed(self.session, second.id)

    # -- MODEL/CLIENT BYPASS ---------------------------------------------

    def test_model_approved_true_has_no_authority(self):
        revision = self.make_revision(requester_user_id=self.requester.id,
                                      candidate=state(approved=True, approval_status="approved"))
        self.assertEqual(get_governance_state(self.session, revision.id), "PENDING_REVIEW")

    # -- DECISIONS ---------------------------------------------------------

    def test_valid_approve_transitions_to_approved(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="approve")
        self.assertEqual(get_governance_state(self.session, revision.id), "APPROVED")

    def test_reject_transitions_and_cannot_release(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="reject")
        self.assertEqual(get_governance_state(self.session, revision.id), "REJECTED")
        with self.assertRaises(ReleaseNotAllowed):
            assert_release_allowed(self.session, revision.id)

    def test_approved_exact_revision_passes_release_check(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="approve")
        assert_release_allowed(self.session, revision.id)  # must not raise
        released = release_advisory(self.session, revision.id)
        self.assertEqual(released["governance_status"], "RELEASED")

    def test_revoked_approval_cannot_release(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="approve")
        apply_decision(self.session, revision_id=revision.id, reviewer=self.other_reviewer, decision="revoke")
        self.assertEqual(get_governance_state(self.session, revision.id), "REVOKED")
        with self.assertRaises(ReleaseNotAllowed):
            assert_release_allowed(self.session, revision.id)

    def test_expired_approval_cannot_release(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        with patch.object(settings, "approval_validity_seconds", 1):
            apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="approve")
        decision = self.session.query(ApprovalDecision).filter_by(action_revision_id=revision.id).one()
        decision_id = decision.id
        # Force it into the past directly via raw SQL: this row is an
        # immutable ORM entity (before_update raises), exactly like every
        # other Phase 5A/5B ledger row -- only a fresh row changes state.
        self.session.execute(ApprovalDecision.__table__.update().where(ApprovalDecision.id == decision_id)
                            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
                            .execution_options(synchronize_session=False))
        self.session.commit()
        self.session.expire_all()
        self.assertEqual(get_governance_state(self.session, revision.id), "EXPIRED")
        with self.assertRaises(ReleaseNotAllowed):
            assert_release_allowed(self.session, revision.id)

    def test_mismatched_request_hash_denies_release(self):
        # Astra finding 2 (HIGH): a forged/corrupted APPROVE row (inserted
        # directly, bypassing apply_decision -- e.g. a raw-SQL or migration
        # bug scenario) whose canonical_request_hash does not match the exact
        # revision must never release, even though the ledger alone computes
        # APPROVED from the row's mere existence.
        revision = self.make_revision(requester_user_id=self.requester.id)
        self.session.execute(insert(ApprovalDecision).values(
            request_id=revision.request_id, action_id=revision.action_id, action_revision_id=revision.id,
            canonical_request_hash="0" * 64, canonical_proposal_hash=revision.canonical_proposal_hash,
            approver_id=self.reviewer.id, decision="APPROVE", decided_at=datetime.now(timezone.utc),
            approval_purpose=revision.approval_purpose, policy_version="governance-5b-v1",
        ))
        self.session.commit()
        self.assertEqual(get_governance_state(self.session, revision.id), "APPROVED")
        with self.assertRaises(ReleaseNotAllowed):
            assert_release_allowed(self.session, revision.id)

    def test_mismatched_proposal_hash_denies_release(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        self.session.execute(insert(ApprovalDecision).values(
            request_id=revision.request_id, action_id=revision.action_id, action_revision_id=revision.id,
            canonical_request_hash=revision.canonical_request_hash, canonical_proposal_hash="0" * 64,
            approver_id=self.reviewer.id, decision="APPROVE", decided_at=datetime.now(timezone.utc),
            approval_purpose=revision.approval_purpose, policy_version="governance-5b-v1",
        ))
        self.session.commit()
        self.assertEqual(get_governance_state(self.session, revision.id), "APPROVED")
        with self.assertRaises(ReleaseNotAllowed):
            assert_release_allowed(self.session, revision.id)

    def test_revoke_requires_prior_approval(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        with self.assertRaises(DecisionNotAllowed):
            apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="revoke")

    # -- CONCURRENCY / REPLAY --------------------------------------------

    def test_duplicate_decision_retry_is_idempotent(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        first = apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="approve")
        second = apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="approve")
        self.assertEqual(first.id, second.id)

    def test_terminal_decision_cannot_be_overwritten(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="approve")
        with self.assertRaises(DecisionConflict):
            apply_decision(self.session, revision_id=revision.id, reviewer=self.other_reviewer, decision="reject")
        # The original decision is untouched.
        self.assertEqual(get_governance_state(self.session, revision.id), "APPROVED")

    def test_decision_row_is_immutable(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        decision = apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="approve")
        decision.reviewer_comment = "tampered"
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.session.flush()
        self.session.rollback()

    # -- BOUNDARY -----------------------------------------------------

    def test_approval_creates_no_new_tool_capability(self):
        before = {tool.name for tool in list_tools()}
        revision = self.make_revision(requester_user_id=self.requester.id)
        apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision="approve")
        release_advisory(self.session, revision.id)
        after = {tool.name for tool in list_tools()}
        self.assertEqual(before, after)
        self.assertEqual(after, {"retrieve_documents", "get_pid_regions", "get_maintenance_history",
                                 "get_work_order", "get_latest_reading", "get_sensor_readings",
                                 "compute_sensor_features"})


class AuthHTTPTests(unittest.TestCase):
    """Real HTTP-layer authentication/authorization checks via TestClient."""

    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine, tables=TABLES)
        self.session = Session(self.engine)
        app.dependency_overrides[get_db] = lambda: self.session
        self.addCleanup(app.dependency_overrides.pop, get_db)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)

        self.requester = User(username="httprequester", role="requester", password_hash=hash_password("pass-req-1"))
        self.reviewer = User(username="httpreviewer", role="reviewer", password_hash=hash_password("pass-rev-1"))
        self.session.add_all([self.requester, self.reviewer])
        self.session.commit()
        self.client = TestClient(app)

    def login(self, client, username, password):
        response = client.post("/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def make_revision(self, *, requester_user_id):
        request = QueryRequest(query="Review pump recommendation", request_id=uuid4())
        revision = create_revision(self.session, request, state(), requester_user_id=requester_user_id)
        self.session.commit()
        return revision

    # -- AUTHENTICATION ---------------------------------------------------

    def test_valid_credentials_authenticate(self):
        self.login(self.client, "httpreviewer", "pass-rev-1")
        me = self.client.get("/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["username"], "httpreviewer")

    def test_invalid_password_rejected(self):
        response = self.client.post("/auth/login", json={"username": "httpreviewer", "password": "wrong"})
        self.assertEqual(response.status_code, 401)

    def test_unknown_user_rejected(self):
        response = self.client.post("/auth/login", json={"username": "nobody", "password": "whatever"})
        self.assertEqual(response.status_code, 401)

    def test_unauthenticated_approval_request_rejected(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        response = self.client.post(f"/approvals/{revision.id}/decision", json={"decision": "approve"})
        self.assertEqual(response.status_code, 401)
        me = self.client.get("/auth/me")
        self.assertEqual(me.status_code, 401)

    def test_client_cannot_forge_role_or_identity(self):
        # A forged/garbage cookie resolves to no one -- never a fallback identity.
        self.client.cookies.set(settings.session_cookie_name, "forged-token-value")
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        # A login response body has no room for a client-chosen role/id either.
        response = self.client.post("/auth/login", json={"username": "httpreviewer", "password": "pass-rev-1",
                                                          "role": "admin"})
        self.assertEqual(response.status_code, 422)

    # -- AUTHORIZATION -----------------------------------------------------

    def test_requester_role_cannot_reach_approvals_list(self):
        self.login(self.client, "httprequester", "pass-req-1")
        response = self.client.get("/approvals")
        self.assertEqual(response.status_code, 403)

    def test_unauthorized_reviewer_cannot_decide(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        self.login(self.client, "httprequester", "pass-req-1")
        response = self.client.post(f"/approvals/{revision.id}/decision", json={"decision": "approve"})
        self.assertEqual(response.status_code, 403)

    # -- MODEL/CLIENT BYPASS ----------------------------------------------

    def test_client_approved_true_has_no_effect_on_decision_endpoint(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        self.login(self.client, "httpreviewer", "pass-rev-1")
        response = self.client.post(f"/approvals/{revision.id}/decision",
                                    json={"decision": "approve", "approved": True})
        self.assertEqual(response.status_code, 422)

    def test_client_approver_id_ignored_as_authority(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        self.login(self.client, "httpreviewer", "pass-rev-1")
        response = self.client.post(f"/approvals/{revision.id}/decision",
                                    json={"decision": "approve", "approver_id": str(uuid4())})
        self.assertEqual(response.status_code, 422)

    # -- DECISIONS / RELEASE via HTTP --------------------------------------

    def test_full_approve_and_release_via_http(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        self.login(self.client, "httpreviewer", "pass-rev-1")
        decide = self.client.post(f"/approvals/{revision.id}/decision", json={"decision": "approve"})
        self.assertEqual(decide.status_code, 200, decide.text)
        self.assertEqual(decide.json()["governance_status"], "APPROVED")

        release = self.client.get(f"/approvals/{revision.id}/release")
        self.assertEqual(release.status_code, 200, release.text)
        self.assertEqual(release.json()["governance_status"], "RELEASED")

    def test_rejected_release_denied_via_http(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        self.login(self.client, "httpreviewer", "pass-rev-1")
        self.client.post(f"/approvals/{revision.id}/decision", json={"decision": "reject"})
        release = self.client.get(f"/approvals/{revision.id}/release")
        self.assertEqual(release.status_code, 403)

    def test_self_approval_denied_via_http(self):
        revision = self.make_revision(requester_user_id=self.reviewer.id)
        self.login(self.client, "httpreviewer", "pass-rev-1")
        response = self.client.post(f"/approvals/{revision.id}/decision", json={"decision": "approve"})
        self.assertEqual(response.status_code, 403)

    def test_wrong_revision_or_hash_denied_via_http(self):
        revision = self.make_revision(requester_user_id=self.requester.id)
        self.login(self.client, "httpreviewer", "pass-rev-1")
        response = self.client.post(f"/approvals/{revision.id}/decision",
                                    json={"decision": "approve", "expected_revision_id": str(uuid4())})
        self.assertEqual(response.status_code, 409)

    def test_logout_revokes_session(self):
        self.login(self.client, "httpreviewer", "pass-rev-1")
        self.assertEqual(self.client.get("/auth/me").status_code, 200)
        self.client.post("/auth/logout")
        self.assertEqual(self.client.get("/auth/me").status_code, 401)


if __name__ == "__main__":
    unittest.main()
