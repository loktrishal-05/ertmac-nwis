"""The evaluation-asset hash guard, required by every sub-phase self-audit
gate in docs/phase4-autonomous-continuation.md. The 75-case benchmark lives
inline in docs/model-evaluation-spec.md rather than as a separate pinned
artifact; this test pins its byte-identical SHA-256 so any read/copy/tune-
against contact that mutates the file fails the gate rather than passing
silently. See docs/phase4-decisions.md D-003."""
import hashlib
import unittest
from pathlib import Path

EVALUATION_SPEC = Path(__file__).resolve().parents[2] / "docs" / "model-evaluation-spec.md"
EXPECTED_SHA256 = "beb507819082539dcdbf3c5b1ff1e30a5590cd071258af6ca8ec475d7f23e0b4"
MANIFEST = {
    "data/evaluation/manifest.json": "ea0184f68615dd8dc3d24bfab731b2c07d0b4e481fee95181d3cb15c0a003c0b",
    "data/evaluation/model_eval_cases.jsonl": "7918c51c3f5c2f3544be013f9be4223f0c23d8385837f8c3d6b176fe1e48a475",
    "data/evaluation/model_eval_config.json": "c3b8998d89eded075c7af33def025f70425d86f5b0f03d646a46004bddde5763",
    "data/evaluation/README.md": "5643ba6e0e0970a809ac7bd43aa00d6980f02f6c5f02691678f2f383b90670e6",
}


class EvaluationAssetGuardTests(unittest.TestCase):
    def test_model_evaluation_spec_is_byte_identical(self):
        digest = hashlib.sha256(EVALUATION_SPEC.read_bytes()).hexdigest()
        self.assertEqual(
            digest, EXPECTED_SHA256,
            "docs/model-evaluation-spec.md changed since the Phase 4 autonomous run began. "
            "If this is an intentional operator edit, repin EXPECTED_SHA256 after confirming "
            "no case content was copied into agent code/prompts/tests/fixtures.",
        )

    def test_evaluation_manifest_assets_are_unchanged(self):
        root = EVALUATION_SPEC.parents[1]
        for relative, expected in MANIFEST.items():
            path = root / relative
            self.assertTrue(path.is_file(), relative)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, relative)


if __name__ == "__main__":
    unittest.main()
