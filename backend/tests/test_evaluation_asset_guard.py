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


class EvaluationAssetGuardTests(unittest.TestCase):
    def test_model_evaluation_spec_is_byte_identical(self):
        digest = hashlib.sha256(EVALUATION_SPEC.read_bytes()).hexdigest()
        self.assertEqual(
            digest, EXPECTED_SHA256,
            "docs/model-evaluation-spec.md changed since the Phase 4 autonomous run began. "
            "If this is an intentional operator edit, repin EXPECTED_SHA256 after confirming "
            "no case content was copied into agent code/prompts/tests/fixtures.",
        )


if __name__ == "__main__":
    unittest.main()
