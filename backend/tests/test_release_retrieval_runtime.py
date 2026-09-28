"""RETRIEVAL RUNTIME release check: deterministic, synthetic, no model loads."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts import release_health as release

SECRET = "postgresql://app:hunter2-secret@db/workbench C:\\secret\\token.txt"


class RetrievalRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(reranking_enabled=True)
        self.embedder, self.reranker = MagicMock(), MagicMock()
        self.embedder.embed.return_value = [[0.01] * 768]
        self.reranker.score.return_value = [3.2, -4.1]
        for target, value in (("app.services.embeddings.get_embeddings", self.embedder),
                              ("app.services.reranking.get_reranker", self.reranker)):
            p = patch(target, return_value=value); p.start(); self.addCleanup(p.stop)

    def run_check(self, timeout=5):
        return release.retrieval_runtime(self.config, timeout=timeout)

    def test_successful_runtime(self):
        ok, detail = self.run_check()
        self.assertTrue(ok)
        self.assertIn("Embedded 1 synthetic string (768-d), reranked 2 synthetic passages", detail)
        texts = self.embedder.embed.call_args.args[0] + self.reranker.score.call_args.args[1]
        self.assertTrue(all("ynthetic" in t for t in texts))  # Fixed synthetic inputs only.

    def test_embedding_load_failure(self):
        self.embedder.embed.side_effect = ImportError("DLL load failed while importing _C: " + SECRET)
        ok, detail = self.run_check()
        self.assertFalse(ok)
        self.assertTrue(detail.startswith("Embedding runtime failed (ImportError)"))
        self.reranker.score.assert_not_called()

    def test_reranker_load_failure(self):
        self.reranker.score.side_effect = OSError("cannot load " + SECRET)
        ok, detail = self.run_check()
        self.assertFalse(ok)
        self.assertTrue(detail.startswith("Reranker runtime failed (OSError)"))

    def test_invalid_outputs_fail(self):
        self.reranker.score.return_value = [-1.0, 2.0]  # Unrelated passage ranked first.
        self.assertTrue(self.run_check()[1].startswith("Reranker runtime failed (ValueError)"))
        self.embedder.embed.return_value = [[0.01] * 384]
        self.assertTrue(self.run_check()[1].startswith("Embedding runtime failed (ValueError)"))

    def test_timeout_is_bounded(self):
        release_worker = threading.Event()
        self.addCleanup(release_worker.set)
        self.embedder.embed.side_effect = lambda *a, **k: release_worker.wait(10) and [[0.01] * 768]
        ok, detail = self.run_check(timeout=0.05)
        self.assertFalse(ok)
        self.assertEqual(detail, "Retrieval runtime exceeded 0.05s; check CPU load, native runtime policy and local model artifacts")

    def test_reranking_disabled_skips_reranker(self):
        self.config.reranking_enabled = False
        ok, detail = self.run_check()
        self.assertTrue(ok)
        self.assertIn("reranking disabled", detail)
        self.reranker.score.assert_not_called()

    def test_no_secret_leakage(self):
        for failing in (self.embedder.embed, self.reranker.score):
            with self.subTest(stage=failing):
                failing.side_effect = RuntimeError(SECRET)
                detail = self.run_check()[1]
                for fragment in ("hunter2", "secret", "postgresql://", "token.txt"):
                    self.assertNotIn(fragment, detail)
                failing.side_effect = None


if __name__ == "__main__":
    unittest.main()
