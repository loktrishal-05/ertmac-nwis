"""Phase E deterministic acceptance. Synthetic configuration and transport; no inference."""
from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import httpx
import test_advanced_c  # Existing application's established import order.
from app.core.config import settings
from app.services import government_resources as gov, language_resources as resources
from scripts import backup, frozen_integrity, nonblind_regression, release_health as release

CLIENT = httpx.Client
ROOT = Path(__file__).resolve().parents[2]


class PhaseETests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ("data", "models", "frontend/dist", "models/bge-base-en-v1.5", "models/bge-reranker-base"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        for name in ("bge-base-en-v1.5", "bge-reranker-base"):
            (self.root / "models" / name / "config.json").write_text("{}")
            (self.root / "models" / name / "model.safetensors").write_bytes(b"synthetic")
        (self.root / "frontend/dist/index.html").write_text("build")
        self.config = settings.model_copy(update={
            "deployment_mode": "confidential", "government_resources_enabled": False, "bhashini_enabled": False,
            "data_root": self.root / "data", "model_root": self.root / "models",
            "database_url": "postgresql+psycopg://application:do-not-print-me@127.0.0.1/workbench",
            "model_runtime": "ollama", "model_name": "qwen3.5:9b", "session_cookie_secure": True,
            "model_context_window": 8192, "model_max_output_tokens": 1024, "model_log_prompts": False,
            "cors_origins": ["https://workbench.internal"], "language_resource_registry": "",
            "stt_url": "", "tts_url": "", "pid_vision_enabled": False,
            "release_model_digests": {}, "automation_secret": "", "automation_user_id": ""})
        self.models = ["qwen3.5:9b", "qwen3.5:4b"]
        self.sent = []

    def transport(self, request):
        self.sent.append(request)
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "test"})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m, "digest": "a" * 64,
                "details": {"quantization_level": "Q4_K_M"}} for m in self.models]})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"model_info": {"test.context_length": 32768}, "capabilities": ["vision"]})
        return httpx.Response(200, json={"status": "ready"})

    def health(self, *, database=True, qdrant=True, current=("head",), speech="unavailable",
               runtime=(True, "synthetic retrieval runtime ok")):
        with ExitStack() as stack:
            stack.enter_context(patch("app.core.config.settings", self.config))
            # Real inference is covered by tests/test_release_retrieval_runtime.py; these models are fake.
            stack.enter_context(patch.object(release, "retrieval_runtime", return_value=runtime))
            stack.enter_context(patch.object(release, "ROOT", self.root))
            stack.enter_context(patch("app.services.readiness.check_postgres", return_value=database))
            stack.enter_context(patch("app.services.readiness.check_qdrant", return_value=qdrant))
            stack.enter_context(patch("app.services.sovereignty_service.get_sovereignty_proof", return_value=SimpleNamespace(status="sovereign")))
            stack.enter_context(patch("app.core.locality.require_private_resolution"))
            stack.enter_context(patch("app.services.local_voice.health", return_value=speech))
            stack.enter_context(patch("sqlalchemy.create_engine"))
            migration = stack.enter_context(patch("alembic.migration.MigrationContext.configure"))
            migration.return_value.get_current_heads.return_value = current
            script = stack.enter_context(patch("alembic.script.ScriptDirectory.from_config"))
            script.return_value.get_heads.return_value = ["head"]
            stack.enter_context(patch("shutil.disk_usage", return_value=SimpleNamespace(free=100 * 1024**3)))
            stack.enter_context(patch("httpx.Client", side_effect=lambda **kw: CLIENT(transport=httpx.MockTransport(self.transport), **kw)))
            return release.collect()

    def status(self, rows, name):
        return next(r["status"] for r in rows if r["name"] == name)

    def test_a_preflight_healthy(self):
        rows = self.health()
        self.assertEqual(release.exit_code(rows), 0)
        self.assertEqual(self.status(rows, "STT"), "WARNING")

    def test_live_speech_and_optional_fallback_are_distinct(self):
        rows = self.health()
        self.assertTrue(all("not configured" in r["detail"] for r in rows if r["name"] in {"STT", "TTS"}))
        self.config.stt_url = "http://127.0.0.1:8765/stt"
        self.config.tts_url = "http://127.0.0.1:8765/tts"
        for health, expected in (("ready", "PASS"), ("unavailable", "WARNING")):
            rows = self.health(speech=health)
            for name in ("STT", "TTS"):
                self.assertEqual(self.status(rows, name), expected)
                self.assertIn("Configured local speech", next(r["detail"] for r in rows if r["name"] == name))

    def test_retrieval_runtime_failure_fails_release(self):
        rows = self.health(runtime=(False, "Embedding runtime failed (ImportError); check native runtime policy"))
        self.assertEqual(self.status(rows, "RETRIEVAL RUNTIME"), "FAIL")
        self.assertEqual(self.status(rows, "RETRIEVAL ARTIFACTS"), "PASS")  # Files alone no longer look healthy.
        self.assertEqual(release.exit_code(rows), 1)

    def test_b_missing_primary(self):
        self.models.remove("qwen3.5:9b")
        rows = self.health()
        self.assertEqual(self.status(rows, "PRIMARY MODEL"), "FAIL")
        self.assertEqual(release.exit_code(rows), 1)

    def test_c_missing_fast_is_release_blocker(self):
        self.models.remove("qwen3.5:4b")
        self.assertEqual(self.status(self.health(), "FAST MODEL"), "FAIL")

    def test_d_postgres_unavailable(self):
        rows = self.health(database=False)
        self.assertEqual(self.status(rows, "DATABASE"), "FAIL")
        self.assertEqual(self.status(rows, "MIGRATIONS"), "FAIL")

    def test_e_qdrant_unavailable(self):
        self.assertEqual(self.status(self.health(qdrant=False), "QDRANT"), "FAIL")

    def test_f_migration_behind(self):
        self.assertEqual(self.status(self.health(current=("old",)), "MIGRATIONS"), "FAIL")

    def register(self, provider="data.gov.in"):
        item = {"name": "Synthetic test public resource", "provider": provider,
                "resource_id": "test", "source": "operator-verified catalogue reference", "license": "test",
                "intended_use": "Public reference", "approved_by": "test operator",
                "base_url": "https://api.data.gov.in/TEST_ONLY_NOT_A_REGISTERED_ENDPOINT",
                "secret_env": "WORKBENCH_GOV_TEST_KEY", "auth_location": "query", "auth_name": "api-key"}
        path = self.root / "registry.json"
        path.write_text(json.dumps([item]))
        self.config.government_resource_registry = str(path)
        return gov.PublicResource.model_validate(item)

    def test_g_h_confidential_rejects_both_connectors_before_network(self):
        for provider in ("data.gov.in", "API Setu"):
            self.register(provider)
            self.config.government_resources_enabled = True
            with patch.object(gov.httpx, "Client") as client, self.assertRaises(resources.PolicyDenied):
                gov.fetch_public_resource("test", data_class="PUBLIC", config=self.config)
            client.assert_not_called()

    def public_fetch(self, handler=None):
        self.config.deployment_mode = "public"
        self.config.government_resources_enabled = True
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, {"WORKBENCH_GOV_TEST_KEY": "never-print-this-key"}))
        stack.enter_context(patch.object(gov.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("8.8.8.8", 443))]))
        stack.enter_context(patch.object(gov.httpx, "Client", side_effect=lambda **kw: CLIENT(
            transport=httpx.MockTransport(handler or (lambda r: httpx.Response(200, json={"records": []}))), **kw)))
        return gov.fetch_public_resource("test", data_class="PUBLIC", config=self.config)

    def test_i_public_opt_in_with_provenance(self):
        self.register()
        result = self.public_fetch()
        self.assertEqual(result["provenance"]["classification"], "PUBLIC_EXTERNAL_OPTIONAL")
        self.assertNotIn("never-print-this-key", json.dumps(result["provenance"]))
        with self.assertRaises(resources.PolicyDenied):
            gov.fetch_public_resource("test", config=self.config)

    def test_j_bhashini_confidential_deployment_blocks_even_public_request(self):
        self.config.bhashini_enabled = True
        resource = next(r for r in resources.builtin() if r.provider == "BHASHINI")
        for classification in ("PUBLIC", "CONFIDENTIAL"):
            self.assertFalse(resources.permitted(resource, classification, self.config))

    def test_k_aikosh_approval_hash_and_actual_artifact(self):
        fields = dict(name="local", provider="AIKosh", source=str(self.root / "artifact"), license="reviewed",
                      intended_use="local speech", deployment="local_downloaded", classification="LOCAL_APPROVED")
        with self.assertRaises(ValueError):
            resources.LanguageResource(**fields)
        (self.root / "artifact").write_bytes(b"local")
        item = resources.LanguageResource(**fields, approved_by="operator", artifact_sha256=hashlib.sha256(b"local").hexdigest())
        self.assertTrue(release._artifact_matches(item))
        (self.root / "artifact").write_bytes(b"changed")
        self.assertFalse(release._artifact_matches(item))

    def test_l_ci_no_blind_execution_and_nonblind_selection(self):
        ci = (ROOT / ".github/workflows/regression.yml").read_text()
        for forbidden in ("benchmark.stage4", "resume_stage4", "--blind", "benchmark/harness/evaluate.py"):
            self.assertNotIn(forbidden, ci)
        self.assertIn("workflow_dispatch", ci)
        self.assertIn("inputs.live_nonblind == true", ci)
        selected, _ = nonblind_regression.selected_inputs()
        self.assertEqual(len(selected), 30)
        self.assertEqual({c["split"] for c in selected}, {"development", "validation"})
        self.assertGreater(frozen_integrity.verify(), 0)

    def test_m_offline_profile(self):
        profile = (ROOT / "infra/offline.env.example").read_text()
        for required in ("WORKBENCH_DEPLOYMENT_MODE=confidential", "MODEL_RUNTIME=ollama",
                         "WORKBENCH_GOVERNMENT_RESOURCES_ENABLED=false", "WORKBENCH_BHASHINI_ENABLED=false", "OLLAMA_NO_CLOUD=1"):
            self.assertIn(required, profile)
        self.assertNotIn("api.openai", profile)

    def test_n_diagnostics_do_not_print_secrets(self):
        self.assertNotIn("do-not-print-me", json.dumps(self.health()))
        output = io.StringIO()
        with patch.object(release, "collect", side_effect=ValueError("secret-password")), redirect_stdout(output):
            self.assertEqual(release.main(["--json"]), 1)
        self.assertNotIn("secret-password", output.getvalue())

    def test_o_backup_validation_and_corruption(self):
        with self.assertRaises(ValueError):
            backup.validate_destination(self.root / "data/backup", [self.root / "data"])
        folder = backup.validate_destination(self.root / "backup", [self.root / "data"])
        folder.mkdir()
        (folder / "data").mkdir()
        (folder / "data/manifest.json").write_text("nested source manifest")
        (folder / "postgres.dump").write_bytes(b"test archive")
        manifest = {"format": 1, "quiesced": True, "data_included": True,
                    "files": {name: backup.checksum(folder / name) for name in ("postgres.dump", "data/manifest.json")}}
        (folder / "manifest.json").write_text(json.dumps(manifest))
        self.assertEqual(backup.verify(folder), manifest)
        (folder / "postgres.dump").write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            backup.verify(folder)
        with self.assertRaises(ValueError):
            backup.create(self.root / "unquiesced")

    def test_p_release_exit_codes(self):
        self.assertEqual(release.exit_code([{"status": "PASS"}, {"status": "WARNING"}]), 0)
        self.assertEqual(release.exit_code([{"status": "FAIL"}]), 1)

    def test_model_digest_mismatch_and_context_block_release(self):
        self.config.release_model_digests = {"qwen3.5:9b": "b" * 64}
        self.assertEqual(self.status(self.health(), "PRIMARY MODEL"), "FAIL")
        self.config.model_context_window = 999999
        self.assertEqual(self.status(self.health(), "RUNTIME CONFIG"), "FAIL")

    def test_public_connector_rate_limit_retry_and_safe_failure(self):
        self.register()
        calls = []
        def limited(request):
            calls.append(request)
            return httpx.Response(429, text="sensitive upstream body")
        with patch.object(gov.time, "sleep"), self.assertRaises(resources.PolicyDenied) as error:
            self.public_fetch(limited)
        self.assertEqual(len(calls), 2)
        self.assertNotIn("never-print-this-key", str(error.exception))
        self.assertNotIn("sensitive upstream body", str(error.exception))

    def test_connector_redirects_and_unsafe_configuration(self):
        item = self.register().model_dump()
        item["base_url"] = "http://127.0.0.1:8000"
        with self.assertRaises(ValueError):
            gov.PublicResource.model_validate(item)
        with self.assertRaises(resources.PolicyDenied):
            self.public_fetch(lambda r: httpx.Response(302, headers={"location": "https://other.gov.in"}))


if __name__ == "__main__":
    unittest.main()
