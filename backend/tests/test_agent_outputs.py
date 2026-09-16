"""Schema-level tests for app/schemas/agent_outputs.py (S1-S7), shared across
Phases 4C-4F. Node-level behaviour (enforcement, prompts, graph wiring) is
tested per sub-phase, e.g. tests/test_agents_knowledge.py for 4C."""
import unittest

from pydantic import ValidationError

from app.schemas.agent_outputs import (
    ActionRecommendation,
    Citation,
    EquipmentTag,
    EquipmentTags,
    GroundedAnswer,
    MaintenanceAssessment,
    MaintenanceHypothesis,
    ProposedAction,
    Refusal,
    SensorInterpretation,
    SensorObservation,
)


def _citation(evidence_id="e1"):
    return Citation(evidence_id=evidence_id, locator="page 1", claim="c")


class SchemaForbidExtraTests(unittest.TestCase):
    def test_grounded_answer_forbids_extra_fields(self):
        with self.assertRaises(ValidationError):
            GroundedAnswer(answer="a", confidence=0.5, bogus=True)

    def test_refusal_forbids_extra_fields(self):
        with self.assertRaises(ValidationError):
            Refusal(status="refused", reason="r", safe_next_step="s", bogus=True)

    def test_equipment_tag_forbids_extra_fields(self):
        with self.assertRaises(ValidationError):
            EquipmentTag(raw_text="P-204", normalized_tag="P-204", equipment_type=None,
                         evidence_id="e1", confidence=0.9, status="unverified", bogus=True)

    def test_action_recommendation_forbids_extra_fields(self):
        with self.assertRaises(ValidationError):
            ActionRecommendation(summary="s", confidence=0.5, bogus=True)


class RefusalStatusTests(unittest.TestCase):
    def test_status_enum_is_closed(self):
        with self.assertRaises(ValidationError):
            Refusal(status="declined", reason="r", safe_next_step="s")

    def test_valid_statuses_accepted(self):
        for status in ("refused", "insufficient_evidence", "clarification_required"):
            Refusal(status=status, reason="r", safe_next_step="s")


class EquipmentTagStatusTests(unittest.TestCase):
    def test_verified_is_a_permitted_enum_value_but_not_default(self):
        # The schema alone cannot enforce "verified only from a registry" --
        # that is app.agents.nodes.knowledge's job (tested separately). This
        # only confirms the enum shape itself matches the S3 spec.
        tag = EquipmentTag(raw_text="x", normalized_tag=None, equipment_type=None,
                            evidence_id="e1", confidence=0.99, status="verified")
        self.assertEqual(tag.status, "verified")

    def test_status_enum_is_closed(self):
        with self.assertRaises(ValidationError):
            EquipmentTag(raw_text="x", normalized_tag=None, equipment_type=None,
                         evidence_id="e1", confidence=0.5, status="confirmed")


class MaintenanceHypothesisEvidenceTests(unittest.TestCase):
    def test_hypothesis_with_neither_evidence_array_is_rejected(self):
        with self.assertRaises(ValidationError):
            MaintenanceHypothesis(text="bearing wear suspected", confidence=0.5)

    def test_hypothesis_with_only_supporting_evidence_is_accepted(self):
        hyp = MaintenanceHypothesis(text="t", supporting_evidence=["e1"], confidence=0.5)
        self.assertEqual(hyp.supporting_evidence, ["e1"])

    def test_hypothesis_with_only_contradicting_evidence_is_accepted(self):
        hyp = MaintenanceHypothesis(text="t", contradicting_evidence=["e1"], confidence=0.5)
        self.assertEqual(hyp.contradicting_evidence, ["e1"])


class ConfidenceBoundsTests(unittest.TestCase):
    def test_grounded_answer_confidence_out_of_bounds_rejected(self):
        with self.assertRaises(ValidationError):
            GroundedAnswer(answer="a", confidence=1.5)
        with self.assertRaises(ValidationError):
            GroundedAnswer(answer="a", confidence=-0.1)

    def test_sensor_observation_requires_evidence_id(self):
        with self.assertRaises(ValidationError):
            SensorObservation(metric="vibration", value_or_trend="rising")


class ProposedActionTests(unittest.TestCase):
    def test_action_class_enum_is_closed(self):
        with self.assertRaises(ValidationError):
            ProposedAction(action="a", action_class="reboot", approval_status="required")

    def test_valid_action_class_accepted(self):
        action = ProposedAction(action="a", action_class="process_change", approval_status="required")
        self.assertEqual(action.action_class, "process_change")


if __name__ == "__main__":
    unittest.main()
