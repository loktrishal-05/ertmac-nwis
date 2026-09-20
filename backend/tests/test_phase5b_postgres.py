"""Opt-in real PostgreSQL approval-decision concurrency/migration/trigger
checks in an isolated schema. Run with WORKBENCH_TEST_POSTGRES=1.

No SQLite concurrency claims for the decision ledger either -- this is the
Phase 5B counterpart to test_phase5a_postgres.py, same isolation technique.
"""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.models import ActionRevision, ApprovalDecision, User
from app.schemas.query import QueryRequest
from app.services.approval import DecisionConflict, DecisionNotAllowed, apply_decision
from app.services.governance import ReleaseNotAllowed, assert_release_allowed, create_revision
from test_phase5a import state


@unittest.skipUnless(os.environ.get("WORKBENCH_TEST_POSTGRES") == "1", "Real PostgreSQL integration not enabled")
class PostgreSQLApprovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_phase5b_" + uuid4().hex
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
            cls.reviewer_a = User(username="pg_reviewer_a", role="reviewer", password_hash=hash_password("a"))
            cls.reviewer_b = User(username="pg_reviewer_b", role="reviewer", password_hash=hash_password("b"))
            cls.requester = User(username="pg_requester", role="requester", password_hash=hash_password("c"))
            session.add_all([cls.reviewer_a, cls.reviewer_b, cls.requester])
            session.commit()
            cls.reviewer_a_id, cls.reviewer_b_id, cls.requester_id = (
                cls.reviewer_a.id, cls.reviewer_b.id, cls.requester.id,
            )

    @classmethod
    def cleanup_schema(cls):
        assert cls.schema.startswith("test_phase5b_") and len(cls.schema) == 45
        with cls.admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))
        cls.admin.dispose()

    def make_revision(self):
        with Session(self.engine) as session:
            request = QueryRequest(query="Review pump recommendation", request_id=uuid4())
            revision = create_revision(session, request, state(), requester_user_id=self.requester_id)
            session.commit()
            return revision.id

    def test_concurrent_approve_and_reject_one_wins(self):
        revision_id = self.make_revision()
        barrier = Barrier(2)

        def decide(reviewer_id, decision):
            with Session(self.engine) as session:
                reviewer = session.get(User, reviewer_id)
                barrier.wait(timeout=10)
                try:
                    result = apply_decision(session, revision_id=revision_id, reviewer=reviewer, decision=decision)
                    session.commit()
                    return ("ok", result.decision)
                except DecisionConflict:
                    session.rollback()
                    return ("conflict", None)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(decide, self.reviewer_a_id, "approve"),
                pool.submit(decide, self.reviewer_b_id, "reject"),
            ]
            outcomes = [future.result(timeout=30) for future in futures]

        winners = [decision for status, decision in outcomes if status == "ok"]
        self.assertEqual(len(winners), 1)
        with Session(self.engine) as session:
            rows = session.scalars(select(ApprovalDecision).where(
                ApprovalDecision.action_revision_id == revision_id,
                ApprovalDecision.decision.in_(("APPROVE", "REJECT")),
            )).all()
            self.assertEqual(len(rows), 1)

    def test_raw_sql_mutation_of_decision_is_rejected(self):
        revision_id = self.make_revision()
        with Session(self.engine) as session:
            reviewer = session.get(User, self.reviewer_a_id)
            decision = apply_decision(session, revision_id=revision_id, reviewer=reviewer, decision="approve")
            session.commit()
            decision_id = decision.id
        with self.assertRaises(DBAPIError), self.engine.begin() as connection:
            connection.execute(text("UPDATE approval_decisions SET decision='REJECT' WHERE id=:id"),
                              {"id": decision_id})
        with self.assertRaises(DBAPIError), self.engine.begin() as connection:
            connection.execute(text("DELETE FROM approval_decisions WHERE id=:id"), {"id": decision_id})

    def test_only_one_terminal_decision_index_enforced_at_db_level(self):
        revision_id = self.make_revision()
        with Session(self.engine) as session:
            reviewer = session.get(User, self.reviewer_a_id)
            apply_decision(session, revision_id=revision_id, reviewer=reviewer, decision="approve")
            session.commit()
        # A second APPROVE/REJECT row for the same revision violates the
        # partial unique index directly, even bypassing the service layer.
        with Session(self.engine) as session, self.assertRaises(DBAPIError):
            session.execute(insert(ApprovalDecision).values(
                request_id=uuid4(), action_id=uuid4(), action_revision_id=revision_id,
                canonical_request_hash="0" * 64, canonical_proposal_hash="0" * 64,
                approver_id=self.reviewer_b_id, decision="REJECT",
                decided_at=text("now()"), approval_purpose="ADVISORY_DRAFT_REVIEW",
                policy_version="governance-5b-v1",
            ))
            session.flush()

    def test_ordinary_requester_cannot_approve_via_direct_service_call(self):
        # Astra finding 1 (HIGH), real PostgreSQL: a different ordinary
        # requester (not this revision's own requester) calling apply_decision
        # directly must be denied by the service itself, not only by the HTTP
        # require_role dependency that a direct call bypasses entirely.
        revision_id = self.make_revision()
        with Session(self.engine) as session:
            requester = session.get(User, self.requester_id)
            with self.assertRaises(DecisionNotAllowed):
                apply_decision(session, revision_id=revision_id, reviewer=requester, decision="approve")
            session.rollback()

    def test_mismatched_decision_hash_denies_release(self):
        # Astra finding 2 (HIGH), real PostgreSQL: a forged APPROVE row
        # inserted directly (bypassing apply_decision) with a hash that does
        # not match the exact ActionRevision must never release.
        revision_id = self.make_revision()
        with Session(self.engine) as session:
            revision = session.get(ActionRevision, revision_id)
            session.execute(insert(ApprovalDecision).values(
                request_id=revision.request_id, action_id=revision.action_id, action_revision_id=revision.id,
                canonical_request_hash="0" * 64, canonical_proposal_hash=revision.canonical_proposal_hash,
                approver_id=self.reviewer_a_id, decision="APPROVE", decided_at=text("now()"),
                approval_purpose=revision.approval_purpose, policy_version="governance-5b-v1",
            ))
            session.commit()
        with Session(self.engine) as session:
            with self.assertRaises(ReleaseNotAllowed):
                assert_release_allowed(session, revision_id)

    def test_migration_downgrade_upgrade_and_metadata(self):
        with patch.object(settings, "database_url", self.url):
            command.downgrade(self.config, "0005_governance_revisions")
            command.upgrade(self.config, "head")
            command.check(self.config)


if __name__ == "__main__":
    unittest.main()
