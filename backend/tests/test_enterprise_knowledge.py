"""Phase C enterprise knowledge lifecycle: real SQL ledger/audit, synthetic sources, no model calls."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy import func, select

import test_advanced_a2  # First: loads the app in its established import order.
from app.core.security import hash_password
from app.db.models import ApprovalDecision, AuditEvent, KnowledgeGap, User
from app.schemas.query import QueryRequest
from app.schemas.verified_knowledge import GapDecision, GapSubmission, KnowledgeCandidate, KnowledgeDecision
from app.services import knowledge_gaps as gaps, knowledge_packs as packs, verified_knowledge as v
from app.services.approval import DecisionNotAllowed
from app.services.audit import verify_chain


class EnterpriseKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.a2 = test_advanced_a2.AdaptiveTests(); self.a2.setUp(); self.addCleanup(self.a2.doCleanups)
        self.f = self.a2.f; self.session = self.f.session
        self.requester, self.reviewer = self.f.requester, self.f.reviewer
        self.admin = User(username="c-admin", role="admin", password_hash=hash_password("a"))
        self.reviewer2 = User(username="c-reviewer2", role="reviewer", password_hash=hash_password("b"))
        self.session.add_all([self.admin, self.reviewer2]); self.session.commit()

    def count(self, event_type):
        return self.session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == event_type))

    def gap(self, actor=None, **updates):
        payload = GapSubmission(**{"subject": "P-204A", "gap_type": "missing_vibration_limit",
                                   "required_evidence": "documented vibration alert limit", **updates})
        value = gaps.submit(self.session, payload, actor or self.requester); self.session.commit(); return value

    def gap_decide(self, gap_id, operation, actor, **fields):
        value = gaps.transition(self.session, gap_id, GapDecision(comment="Reviewed against source", **fields), actor, operation)
        self.session.commit(); return value

    def reverify(self, prior, actor=None):
        item = v.create_candidate(self.session, self.f.payload.model_copy(update={"supersedes_id": prior.id}), actor or self.requester)
        self.session.commit(); return item

    # A-E: authority
    def test_a_candidate_cannot_self_verify(self):
        item = v.create_candidate(self.session, self.f.payload, self.reviewer); self.session.commit()
        with self.assertRaises(DecisionNotAllowed): self.f.decide(item, "verify", self.reviewer)
        self.session.rollback(); self.assertEqual(item.status, "CANDIDATE")

    def test_b_requester_cannot_verify(self):
        item = self.f.candidate()
        with self.assertRaises(DecisionNotAllowed): self.f.decide(item, "verify", self.requester)

    def test_c_reviewer_and_admin_can_verify(self):
        for actor in (self.reviewer, self.admin):
            with self.subTest(role=actor.role):
                item = self.f.candidate(); self.f.decide(item, "verify", actor)
                self.assertEqual((item.status, item.verified_by), ("VERIFIED", actor.id))

    def test_d_forged_client_role_cannot_verify(self):
        item = self.f.candidate()
        for forged in (SimpleNamespace(id=self.requester.id, role="admin"), SimpleNamespace(id=None, role="admin")):
            with self.assertRaises(DecisionNotAllowed): self.f.decide(item, "verify", forged)
            self.session.rollback()

    def test_e_verification_records_authoritative_actor(self):
        item = self.f.candidate()
        # In-memory role is ignored; the stored role and server identity are recorded.
        self.f.decide(item, "verify", SimpleNamespace(id=self.reviewer.id, role="admin"))
        event = self.session.scalars(select(AuditEvent).where(AuditEvent.event_type == "KNOWLEDGE_VERIFIED")).one()
        self.assertEqual(event.actor_id, self.reviewer.id)
        self.assertEqual(event.payload["actor_role"], "reviewer")
        self.assertEqual(event.payload["previous_status"], "CANDIDATE")
        self.assertEqual(event.payload["reason"], "Checked synthetic source")
        self.assertEqual(event.payload["sources"][0]["source_sha256"], self.f.chunk["source_sha256"])
        self.assertEqual(event.payload["sources"][0]["revision"], "R1")
        self.assertEqual(event.payload["asset_scope"]["equipment_tags"], ["P-204A"])
        self.assertEqual(item.verified_by, self.reviewer.id)
        self.assertIsNotNone(item.verified_at)

    # F-J: staleness, revocation, fast path/CAG, re-verification
    def test_f_source_mutation_stales_dependent_knowledge(self):
        item = self.f.verified(); self.f.source.write_bytes(b"revised source")
        changed = v.revalidate(self.session, self.reviewer, self.f.document.id); self.session.commit()
        self.assertEqual([i.id for i in changed], [item.id]); self.assertEqual(item.status, "STALE")
        event = self.session.scalars(select(AuditEvent).where(AuditEvent.event_type == "KNOWLEDGE_STALE")).one()
        self.assertEqual((event.payload["previous_status"], event.actor_kind), ("VERIFIED", "system"))
        with self.assertRaises(DecisionNotAllowed): v.revalidate(self.session, self.requester)

    def test_g_stale_excluded_from_fast_path(self):
        item = self.f.verified(); self.f.document_version.ingestion_metadata = {"revision": "R2", "access_scope": "internal"}
        self.session.commit()
        self.assertIsNone(self.f.lookup()[0]); self.assertEqual(item.status, "STALE")

    def test_h_revoked_excluded_from_fast_path(self):
        item = self.f.verified(); self.f.decide(item, "revoke")
        self.assertIsNone(self.f.lookup()[0])
        event = self.session.scalars(select(AuditEvent).where(AuditEvent.event_type == "KNOWLEDGE_REVOKED")).one()
        self.assertEqual((event.actor_id, event.payload["previous_status"], event.payload["status"]),
                         (self.reviewer.id, "VERIFIED", "REVOKED"))
        self.assertEqual(event.payload["reason"], "Checked synthetic source")
        with self.assertRaises(v.KnowledgeConflict): self.reverify(item)  # REVOKED is terminal.

    def test_i_revoked_member_excluded_from_cag_pack(self):
        pack, member = self.a2.pack()
        request = QueryRequest(query=self.a2.question)
        self.assertIsNotNone(packs.lookup(self.session, request, self.requester)[0])
        self.f.decide(member, "revoke")
        self.assertEqual(packs.lookup(self.session, request, self.requester), (None, "pack_missing_or_stale"))
        self.assertEqual(packs.inspect(self.session, pack.id, self.requester)[1].status, "STALE")

    def test_j_k_reverification_restores_and_preserves_history(self):
        prior = self.f.verified(); prior_verified_at = prior.verified_at
        self.f.decide(prior, "stale")
        successor = self.reverify(prior)
        self.assertIsNone(self.f.lookup()[0])  # A candidate is never served.
        self.f.decide(successor, "verify", self.reviewer2)
        state, meta = self.f.lookup()
        self.assertEqual(meta["knowledge_id"], str(successor.id))
        self.assertEqual((successor.revision, successor.supersedes_id), (2, prior.id))
        # K: the earlier verification and its ledger decision are untouched.
        self.assertEqual((prior.status, prior.verified_by, prior.verified_at), ("STALE", self.reviewer.id, prior_verified_at))
        self.assertEqual(self.session.scalar(select(func.count()).select_from(ApprovalDecision)), 2)
        self.assertEqual(self.count("KNOWLEDGE_VERIFIED"), 2)

    def test_reverifying_verified_item_supersedes_it(self):
        prior = self.f.verified(); successor = self.reverify(prior)
        self.f.decide(successor, "verify", self.reviewer2)
        self.assertEqual(prior.status, "STALE")
        self.assertEqual(self.f.lookup()[1]["knowledge_id"], str(successor.id))

    # L-M: B1/B2 outputs never auto-verify
    def test_l_pid_candidate_cannot_auto_verify(self):
        self.f.chunk["ocr_derived"] = True
        with self.assertRaises(v.SourceChanged):
            v.create_candidate(self.session, self.f.payload.model_copy(update={"origin": "pid_evidence"}), self.requester)
        self.session.rollback(); self.f.chunk["ocr_derived"] = False
        item = self.f.candidate(origin="pid_evidence", origin_reference="pid_region:abc")
        self.assertEqual((item.status, item.verified_by), ("CANDIDATE", None))
        self.assertIsNone(self.f.lookup()[0])
        with self.assertRaises(ValidationError):
            KnowledgeCandidate(**self.f.payload.model_dump(), status="VERIFIED")

    def test_m_maintenance_hypothesis_cannot_auto_verify(self):
        item = self.f.candidate(origin="maintenance_analysis", origin_reference="sensor_window:p204")
        self.assertEqual(item.status, "CANDIDATE"); self.assertIsNone(self.f.lookup()[0])
        self.assertEqual(v.export_item(item)["provenance"]["origin"], "maintenance_analysis")
        # No agent tool can create, verify or resolve knowledge; they are all read-only.
        import app.agents.tools  # noqa: F401
        from app.agents.registry import list_tools
        from app.services.durable_execution import READ_ONLY_TOOLS
        self.assertLessEqual({t.name for t in list_tools()}, READ_ONLY_TOOLS)

    # N-P: gaps
    def test_n_gap_not_resolved_by_model_output(self):
        gap = self.gap()
        with self.assertRaises(v.KnowledgeConflict):  # A generated answer is no evidence.
            self.gap_decide(gap["gap_id"], "resolve", self.reviewer)
        self.session.rollback()
        candidate = self.f.candidate()  # Unverified candidate text is not authority either.
        with self.assertRaises(v.KnowledgeConflict):
            self.gap_decide(gap["gap_id"], "resolve", self.reviewer, knowledge_id=candidate.id)
        self.session.rollback()
        with self.assertRaises(ValidationError):
            GapSubmission(subject="x", gap_type="y", required_evidence="z", status="RESOLVED")
        self.assertEqual(self.session.get(KnowledgeGap, gap["gap_id"]).status, "OPEN")

    def test_o_authorized_human_resolves_gap_with_evidence(self):
        gap = self.gap()
        self.assertEqual(self.gap_decide(gap["gap_id"], "assign", self.reviewer)["status"], "UNDER_REVIEW")
        item = self.f.candidate(origin="knowledge_gap", origin_reference=gap["gap_id"]); self.f.decide(item, "verify")
        value = self.gap_decide(gap["gap_id"], "resolve", self.reviewer, knowledge_id=item.id)
        self.assertEqual((value["status"], value["resolved_by"], value["resolution_knowledge_id"]),
                         ("RESOLVED", self.reviewer.id, item.id))
        self.assertEqual(self.gap_decide(self.gap(subject="P-205")["gap_id"], "resolve", self.admin,
            document_version_id=self.f.document_version.id)["status"], "RESOLVED")
        with self.assertRaises(v.KnowledgeConflict): self.gap_decide(gap["gap_id"], "dismiss", self.reviewer)

    def test_p_unauthorized_gap_resolution_rejected(self):
        item = self.f.verified(); gap = self.gap(actor=self.reviewer2)
        for actor in (self.requester, SimpleNamespace(id=self.requester.id, role="admin"), self.reviewer2):
            with self.subTest(actor=getattr(actor, "role", None)):
                with self.assertRaises(DecisionNotAllowed):
                    self.gap_decide(gap["gap_id"], "resolve", actor, knowledge_id=item.id)
                self.session.rollback()
        with self.assertRaises(DecisionNotAllowed):
            self.gap_decide(gap["gap_id"], "assign", self.reviewer, assignee_id=self.requester.id)

    # Q-T: scope, provenance, durability, audit
    def test_q_access_scope_cannot_be_widened(self):
        for scope in ("public", "restricted"):
            with self.assertRaises(ValidationError): KnowledgeCandidate(**{**self.f.payload.model_dump(), "access_scope": scope})
            with self.assertRaises(ValidationError):
                GapSubmission(subject="x", gap_type="y", required_evidence="z", access_scope=scope)
        self.f.verified(); self.assertIsNone(self.f.lookup(scope="restricted")[0])
        self.assertEqual(self.gap()["access_scope"], "internal")

    def test_r_history_and_provenance_complete(self):
        prior = self.f.verified()
        self.f.decide(prior, "stale"); successor = self.reverify(prior); self.f.decide(successor, "verify", self.reviewer2)
        gap = self.gap(); self.gap_decide(gap["gap_id"], "resolve", self.reviewer, knowledge_id=successor.id)
        self.f.decide(successor, "revoke", self.admin)
        with self.assertRaises(DecisionNotAllowed): v.history(self.session, prior.id, self.requester)
        record = v.history(self.session, prior.id, self.reviewer)
        self.assertEqual([i["knowledge_id"] for i in record["lineage"]], [str(prior.id), str(successor.id)])
        kinds = [e["event_type"] for e in record["events"]]
        for expected in ("KNOWLEDGE_CANDIDATE_CREATED", "APPROVAL_DECISION_APPROVE", "KNOWLEDGE_VERIFIED",
                         "KNOWLEDGE_STALE", "KNOWLEDGE_GAP_TRANSITION", "KNOWLEDGE_REVOKED", "APPROVAL_DECISION_REVOKE"):
            self.assertIn(expected, kinds)
        self.assertEqual([e["sequence_number"] for e in record["events"]], sorted(e["sequence_number"] for e in record["events"]))
        self.assertTrue(verify_chain(self.session)["valid"])

    def test_s_t_retried_verification_is_not_duplicated(self):
        from app.api.routes.verified_knowledge import transaction
        item = self.f.candidate()
        decision = KnowledgeDecision(expected_content_hash=item.content_hash, comment="Human source review")
        run = lambda: v.decide(self.session, item.id, decision, self.reviewer, "verify")
        with patch.object(v, "audit", side_effect=RuntimeError("process interrupted")):
            with self.assertRaises(RuntimeError): transaction(self.session, run)  # Nothing partial survives.
        self.session.expire_all()
        self.assertEqual((item.status, self.count("KNOWLEDGE_VERIFIED")), ("CANDIDATE", 0))
        transaction(self.session, run)
        with self.assertRaises(Exception): transaction(self.session, run)  # Replayed after completion.
        self.assertEqual(self.count("KNOWLEDGE_VERIFIED"), 1)
        self.assertEqual(self.count("APPROVAL_DECISION_APPROVE"), 1)
        gap = self.gap(); self.gap()  # Duplicate submission is deduplicated, not re-audited.
        self.assertEqual(self.count("KNOWLEDGE_GAP_TRANSITION"), 1)
        self.assertEqual(self.session.get(KnowledgeGap, gap["gap_id"]).status, "OPEN")


@unittest.skipUnless(__import__("os").environ.get("WORKBENCH_TEST_POSTGRES") == "1", "PostgreSQL integration not enabled")
class PostgreSQLGapMigrationTests(unittest.TestCase):
    def test_gap_audit_constraint_and_lossy_downgrade_refused(self):
        from pathlib import Path
        from uuid import uuid4
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        from sqlalchemy.orm import Session
        from app.core.config import settings
        schema = "test_c_" + uuid4().hex
        admin = create_engine(settings.database_url); self.addCleanup(admin.dispose)
        with admin.begin() as conn: conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        def cleanup():
            assert schema.startswith("test_c_") and len(schema) == 39
            with admin.begin() as conn: conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        self.addCleanup(cleanup)
        url = make_url(settings.database_url).update_query_dict({"options": f"-csearch_path={schema}"})
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with patch.object(settings, "database_url", url.render_as_string(hide_password=False)):
            command.upgrade(config, "head"); command.check(config)
            engine = create_engine(url); self.addCleanup(engine.dispose)
            with Session(engine) as session:
                submitter = User(username="c-submitter", role="requester", password_hash="fixture")
                session.add(submitter); session.commit()
                gaps.submit(session, GapSubmission(subject="P-204A", gap_type="missing_limit",
                                                   required_evidence="documented limit"), submitter)
                session.commit()  # PostgreSQL accepts the new audit event type.
            engine.dispose()
            with self.assertRaisesRegex(Exception, "refusing lossy downgrade"):  # Gap history exists.
                command.downgrade(config, "0015_durable_execution")


if __name__ == "__main__":
    unittest.main()
