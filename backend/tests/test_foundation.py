"""Foundation checks using the standard library and a live local server."""

import io
import json
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

    def request(self, path, method="GET", body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = Request(self.url + path, data=data, method=method, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 200)
            return json.load(response)

    def test_health(self):
        self.assertEqual(self.request("/health"), {
            "status": "ok", "service": "sovereign-agentic-workbench-backend",
        })

    def test_query(self):
        self.assertEqual(self.request("/query", "POST", {"query": "What is the status of pump P-204?"}), {
            "status": "not_implemented",
            "message": "Agent query processing will be implemented in a later phase.",
        })
        for body in ({}, {"query": "   "}):
            with self.assertRaises(HTTPError) as error:
                self.request("/query", "POST", body)
            self.assertEqual(error.exception.code, 422)

    def test_agents(self):
        self.assertEqual(self.request("/agents/status"), [
            {"name": name, "status": "not_started"} for name in (
                "Orchestrator Agent", "Knowledge Agent", "Safety Agent",
                "Maintenance Agent", "Guardrail Agent",
            )
        ])

    def test_approvals(self):
        self.assertEqual(self.request("/approvals"), [])
        result = self.request("/approvals/00000000-0000-0000-0000-000000000001", "POST")
        self.assertEqual(result["status"], "not_implemented")
        with self.assertRaises(HTTPError) as error:
            self.request("/approvals/invalid", "POST")
        self.assertEqual(error.exception.code, 422)

    def test_documents(self):
        self.assertEqual(self.request("/documents/ingest", "POST"), {
            "status": "not_implemented",
            "message": "Document ingestion will be implemented in the RAG phase.",
        })

    def test_audit_and_sovereignty(self):
        self.assertEqual(self.request("/audit/log"), [])
        self.assertEqual(self.request("/sovereignty/proof"), {
            "external_ai_calls": 0, "cloud_ai_enabled": False,
            "inference_mode": "local_only", "status": "sovereign",
        })

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
        self.assertEqual(len(models.__all__), 9)
        self.assertEqual(len(Base.metadata.tables), 9)
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
