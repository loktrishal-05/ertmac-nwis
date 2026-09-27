"""The evaluation-asset hash guard, required by every sub-phase self-audit
gate in docs/phase4-autonomous-continuation.md. The 75-case benchmark lives
inline in docs/model-evaluation-spec.md rather than as a separate pinned
artifact; this test pins its byte-identical SHA-256 so any read/copy/tune-
against contact that mutates the file fails the gate rather than passing
silently. See docs/phase4-decisions.md D-003."""
import hashlib
import subprocess
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


def canonical_checkout_bytes(raw, committed):
    """Accept only exact Git bytes or their uniform Windows checkout encoding."""
    if raw != committed and not (b"\r" not in committed and raw == committed.replace(b"\n", b"\r\n")):
        raise AssertionError("Frozen asset differs from Git beyond checkout line endings")
    return committed


def canonical_asset_bytes(path):
    root = EVALUATION_SPEC.parents[1]
    relative = path.relative_to(root).as_posix()
    committed = subprocess.check_output(["git", "show", "HEAD:" + relative], cwd=root)
    return canonical_checkout_bytes(path.read_bytes(), committed)


class EvaluationAssetGuardTests(unittest.TestCase):
    def test_checkout_conversion_does_not_hide_mutation(self):
        committed = b"first\nsecond\n"
        for raw in (committed, b"first\r\nsecond\r\n"):
            self.assertEqual(canonical_checkout_bytes(raw, committed), committed)
        for raw in (b"changed\r\nsecond\r\n", b"first\r\nsecond\n",
                    b"first\rsecond\r", b"first\nsecond", committed + b"\n"):
            with self.subTest(raw=raw), self.assertRaises(AssertionError):
                canonical_checkout_bytes(raw, committed)

    def test_model_evaluation_spec_is_byte_identical(self):
        digest = hashlib.sha256(canonical_asset_bytes(EVALUATION_SPEC)).hexdigest()
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
            self.assertEqual(hashlib.sha256(canonical_asset_bytes(path)).hexdigest(), expected, relative)


if __name__ == "__main__":
    unittest.main()
