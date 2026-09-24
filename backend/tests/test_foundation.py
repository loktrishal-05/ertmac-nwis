"""Foundation checks using the standard library and a live local server."""

import io
import json
import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import configure_mappers

from app.core.config import Settings
from app.db.base import Base
from app.db import models
from app.db.session import engine
from app.main import app

BACKEND = Path(__file__).resolve().parents[1]


class FoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.url = f"http://127.0.0.1:{port}"
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=BACKEND, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        cls.addClassCleanup(cls.stop_server)
        for _ in range(100):
            try:
                with urlopen(cls.url + "/health", timeout=1):
                    return
            except URLError:
                if cls.server.poll() is not None:
                    raise RuntimeError("Uvicorn exited before startup")
                time.sleep(0.1)
        raise RuntimeError("Uvicorn startup timed out")

    @classmethod
    def stop_server(cls):
        cls.server.terminate()
        cls.server.wait(timeout=10)

    def request(self, path, method="GET", body=None, timeout=5):
        data = json.dumps(body).encode() if body is not None else None
        request = Request(self.url + path, data=data, method=method, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=timeout) as response:
            self.assertEqual(response.status, 200)
            return json.load(response)

    def test_health(self):
        self.assertEqual(self.request("/health"), {
            "status": "ok", "service": "sovereign-agentic-workbench-backend",
        })

    @unittest.skipUnless(os.environ.get("WORKBENCH_TEST_LIVE_MODEL") == "1",
                         "Live local-model /query smoke not enabled")
    def test_query(self):
        # Phase 4B: /query now runs the real router graph, so the route it
        # picks depends on the live model's own classification rather than a
        # fixed placeholder. Assert the (extended, not broken) contract shape
        # instead of one hardcoded route.
        # As of Phase 4C-4E, knowledge/maintenance/safety/combined_safety_maintenance
        # (plus the always-terminal guardrail_refusal/clarification) are real agents
        # with an S1-S7 agent_result.schema, not the flat not_implemented stub shape;
        # process_optimization remains the one stub pending 4F. Branch on which the
        # live model actually picked rather than assuming either shape.
        # Opt-in only (WORKBENCH_TEST_LIVE_MODEL=1), mirroring WORKBENCH_TEST_POSTGRES
        # in test_phase5a_postgres.py: this is a live-model integration probe, not a
        # deterministic unit test -- its wall-clock time depends on this machine's
        # token throughput (measured ~3.3 tok/s for qwen3.5:9b/CPU on 2026-09-20;
        # see docs/phase5a-validation.md), not on this code. A generous client-side
        # timeout matches that measured throughput rather than papering over it.
        from app.agents.prompts.router import ROUTE_NAMES
        STUB_ROUTES = {"process_optimization"}
        body = self.request("/query", "POST", {"query": "What is the status of pump P-204?"}, timeout=600)
        self.assertIn(body["route"], ROUTE_NAMES)
        if body["route"] in STUB_ROUTES:
            self.assertEqual(body["agent_result"]["status"], "not_implemented")
        else:
            self.assertIn(body["agent_result"]["schema"], ("S1", "S3", "S4", "S5", "S6", "S7"))
        self.assertIsInstance(body["run_id"], str)
        self.assertIsInstance(body["evidence"], list)
        for body in ({}, {"query": "   "}, {"query": "x", "model": "other"}):
            with self.assertRaises(HTTPError) as error:
                self.request("/query", "POST", body)
            self.assertEqual(error.exception.code, 422)

    def test_agents(self):
        from app.agents.prompts.router import ROUTE_NAMES
        body = self.request("/agents/status")
        self.assertEqual({route["route"] for route in body["routes"]}, set(ROUTE_NAMES))
        self.assertEqual({route["status"] for route in body["routes"]}, {"implemented", "guardrail"})
        self.assertTrue(len(body["tools"]) >= 1)
        self.assertTrue(all(tool["read_only"] for tool in body["tools"]))
        self.assertIn("reachable", body["gateway"])

    def test_approvals(self):
        # Phase 5B: GET /approvals now lists real pending governed revisions
        # for an authenticated reviewer/admin; unauthenticated is rejected.
        # See test_phase5b.py for the authenticated contract.
        with self.assertRaises(HTTPError) as error:
            self.request("/approvals")
        self.assertEqual(error.exception.code, 401)
        result = self.request("/approvals/00000000-0000-0000-0000-000000000001", "POST")
        self.assertEqual(result["status"], "not_implemented")
        with self.assertRaises(HTTPError) as error:
            self.request("/approvals/invalid", "POST")
        self.assertEqual(error.exception.code, 422)

    def test_documents(self):
        with self.assertRaises(HTTPError) as error:
            self.request("/documents/ingest", "POST")
        self.assertEqual(error.exception.code, 422)

    def test_audit_and_sovereignty(self):
        # Phase 5C: GET /audit/log is now real (reviewer/admin only) rather
        # than a permanent []. See test_phase5c.py for the authenticated
        # contract and the tamper-evident chain itself.
        with self.assertRaises(HTTPError) as error:
            self.request("/audit/log")
        self.assertEqual(error.exception.code, 401)
        proof = self.request('/sovereignty/proof')
        self.assertEqual(proof['external_ai_calls'], 0)
        self.assertFalse(proof['cloud_ai_enabled'])
        self.assertEqual(proof['status'], 'sovereign')
        self.assertFalse(proof['network_egress_enforced'])

    def test_cors(self):
        for origin in Settings().cors_origins:
            request = Request(self.url + "/health", headers={"Origin": origin})
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.headers["Access-Control-Allow-Origin"], origin)
            request = Request(self.url + "/query", method="OPTIONS", headers={
                "Origin": origin, "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            })
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.headers["Access-Control-Allow-Origin"], origin)

    def test_metadata_and_offline_migration(self):
        configure_mappers()
        self.assertEqual(len(models.__all__), 23)
        self.assertEqual(len(Base.metadata.tables), 24)
        self.assertEqual(engine.dialect.name, "postgresql")
        self.assertEqual(engine.dialect.driver, "psycopg")
        self.assertIn("/health", app.openapi()["paths"])
        output = io.StringIO()
        config = Config(str(BACKEND / "alembic.ini"), output_buffer=output)
        command.upgrade(config, "head", sql=True)
        sql = output.getvalue()
        for table in Base.metadata.sorted_tables:
            self.assertIn(f"CREATE TABLE {table.name} (", sql)
            self.assertEqual(list(table.primary_key.columns)[0].name, "id")
        self.assertIn("JSONB", sql)
        self.assertNotIn("DROP TABLE", sql)


if __name__ == "__main__":
    unittest.main()
