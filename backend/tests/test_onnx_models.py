"""ONNX retrieval artifacts: never fetched outside the hosted demo, and never used if their checksum is wrong."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.services import onnx_models


class OnnxArtifactTest(unittest.TestCase):
    def test_missing_artifacts_are_not_downloaded_outside_hosted_demo(self):
        with tempfile.TemporaryDirectory() as root, patch.object(settings, "model_root", Path(root)), \
                patch.object(settings, "hosted_demo", False), patch("urllib.request.urlretrieve") as fetch:
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                onnx_models.artifact_dir("bge-base-en-v1.5")
            fetch.assert_not_called()

    def test_tampered_artifact_is_rejected_and_removed(self):
        with tempfile.TemporaryDirectory() as root, patch.object(settings, "model_root", Path(root)), \
                patch.object(settings, "hosted_demo", True), patch("urllib.request.urlretrieve") as fetch:
            model = Path(root, "bge-reranker-base-onnx", "model_int8.onnx")
            model.parent.mkdir()
            model.write_bytes(b"not the pinned model")
            with self.assertRaisesRegex(RuntimeError, "integrity"):
                onnx_models.artifact_dir("bge-reranker-base")
            self.assertFalse(model.exists())
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
