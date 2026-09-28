"""Deterministic crash/restart tests against a file-backed recovery store."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.agents.checkpoint import SQLCheckpointSaver, config_for
from app.agents.registry import get_tool
from app.core.config import settings
from app.db.base import Base
from app.db.models import User, AuditEvent, ApprovalDecision
from app.db.models.durable_execution import DurableExecution, ExecutionOperation, GraphCheckpoint, GraphWrite
from app.schemas.query import QueryRequest
from app.services import durable_execution as durable
from app.services.approval import apply_decision
from app.services.model_gateway import ModelTimeoutError, StructuredOutputError
from test_phase5a import TABLES


class DurableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.url = getattr(self, "postgres_url", "sqlite:///" + str(Path(self.temp.name) / "recovery.db"))
        self.engine = create_engine(self.url)
        Base.metadata.create_all(self.engine, tables=TABLES + [m.__table__ for m in
            (DurableExecution, ExecutionOperation, GraphCheckpoint, GraphWrite)])
        self.session = Session(self.engine, expire_on_commit=False)
        self.addCleanup(lambda: self.engine.dispose())
        self.addCleanup(lambda: self.session.close())
        suffix = uuid4().hex
        self.owner = User(username="owner" + suffix, role="requester", password_hash="unused")
        self.reviewer = User(username="reviewer" + suffix, role="reviewer", password_hash="unused")
        self.other = User(username="other" + suffix, role="requester", password_hash="unused")
        self.session.add_all([self.owner, self.reviewer, self.other])
        self.session.commit()
        self.request = QueryRequest(query="Review pump maintenance recommendation", request_id=uuid4())
        self.calls = 0
        self.route = patch("app.agents.graph.router_node", return_value={"route": "maintenance", "route_reasoning": "PRIVATE_CHAIN"}).start()
        self.node = patch("app.agents.graph.maintenance_node", side_effect=self.answer).start()
        self.gateway = patch("app.agents.graph.get_model_gateway").start()
        patch("app.services.execution_observability.attach", return_value={}).start()
        self.addCleanup(patch.stopall)

    def answer(self, *args, **kwargs):
        self.calls += 1
        return {"agent_result": {"schema": "S4", "output": {"summary": "Review required"}},
                "human_approval_required": True, "evidence": []}

    def start(self):
        return durable.start(self.session, self.request, self.owner)

    def resume(self):
        return durable.resume(self.session, self.request.request_id, self.owner)

    def restart(self):
        owner_id = self.owner.id
        self.session.close()
        self.engine.dispose()
        self.engine = create_engine(self.url)
        self.session = Session(self.engine, expire_on_commit=False)
        self.owner = self.session.get(User, owner_id)

    def test_checkpoint_and_durable_wait(self):
        result = self.start()
        self.assertEqual(result["status"], "WAITING_APPROVAL", result)
        self.assertGreater(result["checkpoint_version"], 0)
        self.assertEqual(result["current_node"], "approval")
        self.assertEqual(result["execution_id"], self.request.request_id)

    def test_completed_nodes_survive_application_restart(self):
        self.start()
        self.restart()
        self.assertEqual(self.resume()["status"], "WAITING_APPROVAL")
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.route.call_count, 1)

    def test_interrupted_model_node_recovers(self):
        self.node.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.start()
        self.restart()
        self.node.side_effect = self.answer
        result = self.resume()
        self.assertEqual(result["status"], "WAITING_APPROVAL", result)
        self.assertEqual(self.route.call_count, 1)
        self.assertEqual(result["retry_count"], 1)

    def test_tool_not_repeated_after_model_timeout(self):
        tool = get_tool("get_latest_reading")
        first = True
        def answer(*args, **kwargs):
            nonlocal first
            tool.invoke(self.session, {"equipment_tag": "P-101", "sensor_tag": "PT-101"})
            if first:
                first = False
                raise ModelTimeoutError("timeout")
            return self.answer()
        self.node.side_effect = answer
        with patch.object(tool, "adapter", return_value=({"reading": None}, [])) as adapter:
            result = self.start()
            self.assertEqual(result["status"], "FAILED", result)
            self.restart()
            result = self.resume()
            self.assertEqual(result["status"], "WAITING_APPROVAL", result)
            self.assertEqual(adapter.call_count, 1)

    def decide(self, decision):
        result = self.start()
        revision = result["response"]["action_revision_id"]
        from uuid import UUID
        apply_decision(self.session, revision_id=UUID(revision), reviewer=self.reviewer, decision=decision)
        self.session.commit()
        return revision

    def test_approval_resumes_from_gate(self):
        self.decide("approve")
        self.restart()
        result = self.resume()
        self.assertEqual(result["status"], "COMPLETED", result)
        self.assertEqual(result["response"]["governance_status"], "APPROVED")
        self.assertEqual(self.calls, 1)

    def test_rejection_terminates(self):
        self.decide("reject")
        self.assertEqual(self.resume()["status"], "REJECTED")
        self.assertEqual(self.calls, 1)

    def test_wait_cannot_self_resume(self):
        self.start()
        self.assertEqual(self.resume()["status"], "WAITING_APPROVAL")
        self.assertEqual(self.session.scalar(select(func.count()).select_from(ApprovalDecision)
            .where(ApprovalDecision.request_id == self.request.request_id)), 0)

    def test_unauthorized_resume_and_status(self):
        self.start()
        for fn in (durable.resume, durable.status):
            with self.assertRaises(PermissionError):
                fn(self.session, self.request.request_id, self.other)
        self.other.role = "admin"
        with self.assertRaises(PermissionError):
            durable.resume(self.session, self.request.request_id, self.other)
        self.session.rollback()

    def test_transient_failure_retry(self):
        self.node.side_effect = ModelTimeoutError("transport")
        result = self.start()
        self.assertEqual(result["retry_class"], "RETRYABLE_INFRASTRUCTURE")
        self.node.side_effect = self.answer
        self.assertEqual(self.resume()["status"], "WAITING_APPROVAL")

    def test_validation_is_not_retried(self):
        self.node.side_effect = StructuredOutputError("PRIVATE_REJECTED", raw_text="PRIVATE_RAW")
        result = self.start()
        self.assertEqual(result["retry_class"], "NON_RETRYABLE_VALIDATION")
        with self.assertRaises(durable.RecoveryConflict):
            self.resume()
        self.assertEqual(self.node.call_count, 1)

    def test_safety_model_pin_never_downgrades(self):
        self.node.side_effect = ModelTimeoutError("timeout")
        result = self.start()
        self.assertEqual(result["selected_model"], settings.primary_model)
        with patch.object(settings, "primary_model", settings.fast_model):
            with self.assertRaises(durable.RecoveryConflict):
                self.resume()
        self.assertEqual(self.node.call_count, 1)

    def test_audit_events_not_duplicated(self):
        self.decide("approve")
        count = self.session.scalar(select(func.count()).select_from(AuditEvent))
        self.resume()
        self.resume()
        self.start()
        self.assertEqual(self.session.scalar(select(func.count()).select_from(AuditEvent)), count)

    def test_checkpoint_contains_no_hidden_reasoning(self):
        self.start()
        payloads = []
        for model, fields in ((GraphCheckpoint, ("checkpoint", "meta")), (GraphWrite, ("value",)),
                              (ExecutionOperation, ("result",))):
            for row in self.session.scalars(select(model)):
                payloads.extend(getattr(row, name) for name in fields)
        self.assertNotIn("PRIVATE_CHAIN", json.dumps(payloads))
        self.assertNotIn("route_reasoning", json.dumps(payloads))

    def test_receipt_closes_completion_checkpoint_gap(self):
        original = SQLCheckpointSaver.put_writes
        def crash(saver, config, writes, task_id, task_path=""):
            if any(channel == "agent_result" for channel, _ in writes):
                raise KeyboardInterrupt()
            return original(saver, config, writes, task_id, task_path)
        with patch.object(SQLCheckpointSaver, "put_writes", crash):
            with self.assertRaises(KeyboardInterrupt):
                self.start()
        self.restart()
        self.assertEqual(self.resume()["status"], "WAITING_APPROVAL")
        self.assertEqual(self.calls, 1)

    def test_pending_writes_and_history(self):
        self.start()
        saver = SQLCheckpointSaver(self.engine)
        history = list(saver.list(config_for(self.request.request_id)))
        self.assertGreater(len(history), 2)
        self.assertTrue(history[0].pending_writes)

    def test_ambiguous_side_effect_fails_closed(self):
        self.start()
        runtime = durable.Runtime(self.engine, self.request.request_id, self.session)
        with self.assertRaises(KeyboardInterrupt):
            runtime.operation("external:test", lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
        with self.assertRaises(durable.RecoveryConflict):
            runtime.operation("external:test", lambda: "must not repeat")

    def test_hard_process_exit_and_fresh_process_recovery(self):
        script = '''
import os
from uuid import UUID
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.models import User
from app.main import app
from app.schemas.query import QueryRequest
from app.services.durable_execution import start
engine = create_engine(os.environ["A2_TEST_DB"])
with Session(engine) as session:
    owner = session.get(User, UUID(os.environ["A2_TEST_OWNER"]))
    request = QueryRequest(query="Review pump maintenance recommendation", request_id=UUID(os.environ["A2_TEST_REQUEST"]))
    with patch("app.agents.graph.get_model_gateway"), patch("app.agents.graph.router_node", return_value={"route": "maintenance"}), patch("app.agents.graph.maintenance_node", side_effect=lambda *a, **k: os._exit(23)):
        start(session, request, owner)
'''
        env = dict(os.environ, A2_TEST_DB=self.url, A2_TEST_OWNER=str(self.owner.id),
                   A2_TEST_REQUEST=str(self.request.request_id), PYTHONDONTWRITEBYTECODE="1")
        child = subprocess.run([sys.executable, "-B", "-c", script], env=env, capture_output=True, timeout=30)
        self.assertEqual(child.returncode, 23, child.stderr.decode(errors="replace"))
        self.restart()
        result = durable.status(self.session, self.request.request_id, self.owner)
        self.assertEqual(result["status"], "INTERRUPTED")
        self.assertEqual(self.resume()["status"], "WAITING_APPROVAL")
        self.assertEqual(self.route.call_count, 0)

    def test_http_ownership_and_authentication(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.deps import get_current_user
        from app.api.routes.executions import router
        from app.db.session import get_db
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.session
        with TestClient(app) as client:
            self.assertEqual(client.post("/executions", json=self.request.model_dump(mode="json")).status_code, 401)
            app.dependency_overrides[get_current_user] = lambda: self.owner
            result = client.post("/executions", json=self.request.model_dump(mode="json"))
            self.assertEqual(result.status_code, 200, result.text)
            app.dependency_overrides[get_current_user] = lambda: self.other
            self.assertEqual(client.get(f"/executions/{self.request.request_id}").status_code, 403)
            self.assertEqual(client.post(f"/executions/{self.request.request_id}/resume").status_code, 403)

    def test_governance_receipt_and_audit_rollback_together(self):
        original = durable.encode
        def fail_receipt(value):
            if isinstance(value, dict) and "response" in value:
                raise ConnectionError("receipt unavailable")
            return original(value)
        with patch.object(durable, "encode", side_effect=fail_receipt):
            result = self.start()
        self.assertEqual(result["status"], "FAILED", result)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(AuditEvent)
            .where(AuditEvent.request_id == self.request.request_id)), 0)
        result = self.resume()
        self.assertEqual(result["status"], "WAITING_APPROVAL", result)
        self.assertEqual(self.calls, 1)

    def test_evidence_round_trip(self):
        from app.agents.evidence import csv_row_evidence
        ref = csv_row_evidence(source_filename="readings.csv", source_sha256="a" * 64, source_row_number=1)
        restored = durable.decode(durable.encode(({"records": []}, [ref])))
        self.assertEqual(restored, ({"records": []}, [ref]))


@unittest.skipUnless(os.environ.get("WORKBENCH_TEST_POSTGRES") == "1", "Real PostgreSQL integration not enabled")
class PostgresDurableTests(DurableTests):
    @classmethod
    def setUpClass(cls):
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import text
        from sqlalchemy.engine import make_url
        cls.schema = "test_durable_" + uuid4().hex
        cls.admin = create_engine(settings.database_url)
        with cls.admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.addClassCleanup(cls.cleanup_schema)
        cls.postgres_url = make_url(settings.database_url).update_query_dict(
            {"options": "-csearch_path=" + cls.schema}).render_as_string(hide_password=False)
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with patch.object(settings, "database_url", cls.postgres_url):
            command.upgrade(config, "head")
            command.check(config)
            command.downgrade(config, "0014_product_integration")
            command.upgrade(config, "head")
            command.check(config)

    @classmethod
    def cleanup_schema(cls):
        from sqlalchemy import text
        assert cls.schema.startswith("test_durable_") and len(cls.schema) == 45
        with cls.admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))
        cls.admin.dispose()

    def test_concurrent_recovery_is_excluded(self):
        self.start()
        with durable.execution_lock(self.engine, self.request.request_id):
            with self.assertRaises(durable.RecoveryConflict):
                self.resume()


if __name__ == "__main__":
    unittest.main()
