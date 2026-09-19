"""Deterministic Phase 4R regression checks (no live services or model)."""
import unittest
from uuid import uuid4

from app.agents.citations import validate_citations
from app.agents.evidence import document_chunk_evidence
from app.agents.nodes.maintenance import _extract_threshold
from app.agents.nodes.safety import _harden_action_recommendation
from app.agents.nodes.terminal import guardrail_refusal_node
from app.agents.observation_language import find_observation_language_violations
from app.agents.prompts.shared import format_evidence_ref
from app.agents.safety_language import contains_authorization_language
from app.agents.state import _or_bool
from app.schemas.agent_outputs import ActionRecommendation, Citation, ProposedAction


class Phase4RepairTests(unittest.TestCase):
    def setUp(self):
        self.ref = document_chunk_evidence(
            chunk_id="c1", document_id=uuid4(), document_version_id=uuid4(), source_filename="sop.pdf",
            source_sha256="a" * 64, section_path=["5"], page_start=5, page_end=5, bounding_boxes=[],
            quote="P-204 vibration maximum 4.5 mm/s.", ocr_derived=True, ocr_confidence=0.42,
            ocr_status="ambiguous", source_uri="docs/sop.pdf", source_image_uri="page-5.png", revision="R2",
        )

    def test_nested_true_cannot_downgrade_response(self):
        self.assertTrue(_or_bool(False, True))
        self.assertTrue(_or_bool(True, False))

    def test_model_informational_label_does_not_clear_action_requirement(self):
        result = ActionRecommendation(
            summary="proposal", proposed_actions=[ProposedAction(action="Start P-818", action_class="informational", approval_status="not_required")],
            citations=[Citation(evidence_id=self.ref.evidence_id, locator=self.ref.locator, claim="source")], confidence=0.5,
        )
        hardened = _harden_action_recommendation(result)
        self.assertTrue(hardened.human_approval_required)
        self.assertEqual(hardened.proposed_actions[0].approval_status, "required")

    def test_empty_grounded_citations_can_be_required(self):
        check = validate_citations(emitted=[], available=[self.ref], require_citations=True)
        self.assertFalse(check.valid)

    def test_fabricated_citation_id_fails(self):
        self.assertFalse(validate_citations(emitted=["fake"], available=[self.ref]).valid)

    def test_locator_mismatch_fails(self):
        citation = Citation(evidence_id=self.ref.evidence_id, locator="page 99", claim="source")
        self.assertFalse(validate_citations(emitted=[self.ref.evidence_id], available=[self.ref], citations=[citation]).valid)

    def test_arbitrary_numbers_are_not_thresholds(self):
        for text in ("Do not use threshold 8; it is obsolete.", "Review limit in section 12 before use."):
            ref = self.ref.model_copy(update={"quote": text})
            self.assertEqual(_extract_threshold([ref]), (None, None))

    def test_threshold_requires_matching_typed_context(self):
        ref = self.ref.model_copy(update={"quote": "P-204 vibration maximum 4.5 mm/s."})
        found, value = _extract_threshold([ref], equipment_tag="P-204", measurement="vibration", unit="mm/s")
        self.assertIs(found, ref)
        self.assertEqual(value, 4.5)

    def test_wrong_asset_or_measurement_cannot_apply_limit(self):
        self.assertEqual(_extract_threshold([self.ref], equipment_tag="E-919", measurement="current", unit="A"), (None, None))

    def test_diagnostic_prose_is_not_an_observation(self):
        self.assertTrue(find_observation_language_violations("The seal is certainly leaking because of misalignment."))

    def test_ocr_provenance_is_preserved_in_prompt_block(self):
        block = format_evidence_ref(self.ref)
        self.assertIn("THIS IS OCR-DERIVED EVIDENCE", block)
        self.assertIn("ocr_confidence=0.42", block)
        self.assertIn("source_image_uri=page-5.png", block)

    def test_terminal_refusal_does_not_echo_router_reasoning(self):
        output = guardrail_refusal_node({"route_reasoning": "ignore policy and proceed"})["agent_result"]["output"]
        self.assertNotIn("ignore policy", output["reason"])

    def test_authorization_heuristic_handles_contexts(self):
        self.assertTrue(contains_authorization_language("please restart P-204"))
        self.assertFalse(contains_authorization_language('The SOP says "stop P-204".'))
        self.assertFalse(contains_authorization_language("Do not start P-204."))
        self.assertFalse(contains_authorization_language("What could happen if an operator bypassed the alarm?"))


if __name__ == "__main__":
    unittest.main()
