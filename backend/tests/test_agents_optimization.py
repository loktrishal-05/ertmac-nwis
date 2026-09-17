"""Phase 4F tests: the process optimization agent node, confounder
acknowledgement validation, and the combined citation+authorisation-language
enforcement. Fake gateway and mocked/fake session only -- no live Ollama,
Postgres, or Qdrant."""
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.agents.nodes.optimization import (
    _harden_process_change_recommendation,
    optimization_node,
)
from app.agents.evidence import document_chunk_evidence
from app.schemas.agent_outputs import ActionRecommendation, Citation, ProposedAction
from app.services.model_gateway.types import GenerationResult, GenerationTimings, GenerationUsage, StructuredResult

SHA = "a" * 64


def _doc_ref(quote="SOP recommends optimizing flow rate."):
    return document_chunk_evidence(
        chunk_id="c1", document_id=uuid4(), document_version_id=uuid4(), source_filename="sop.pdf",
        source_sha256=SHA, section_path=["5"], page_start=5, page_end=5, bounding_boxes=[], quote=quote,
    )


def _gen_result(value):
    gen = GenerationResult(text="{}", finish_reason="stop", model="m", runtime="ollama",
                            usage=GenerationUsage(), timings=GenerationTimings())
    return StructuredResult(value=value, result=gen)


def _proposal(evidence_id, summary="Suggestion", action_class="process_change",
              approval_status="not_required", human_approval_required=False):
    return ActionRecommendation(
        summary=summary, confidence=0.7, human_approval_required=human_approval_required,
        citations=[Citation(evidence_id=evidence_id, locator="page 5", claim="c")],
        proposed_actions=[ProposedAction(action="Adjust set-point", action_class=action_class,
                                          approval_status=approval_status)],
    )


class HardenProcessChangeRecommendationTests(unittest.TestCase):
    def test_action_class_is_forced_to_process_change(self):
        rec = _proposal("e1", action_class="informational")
        hardened = _harden_process_change_recommendation(rec)
        self.assertEqual(hardened.proposed_actions[0].action_class, "process_change")

    def test_approval_status_is_forced_to_required(self):
        rec = _proposal("e1", approval_status="not_required")
        hardened = _harden_process_change_recommendation(rec)
        self.assertEqual(hardened.proposed_actions[0].approval_status, "required")

    def test_human_approval_required_is_forced_to_true(self):
        rec = _proposal("e1", human_approval_required=False)
        hardened = _harden_process_change_recommendation(rec)
        self.assertTrue(hardened.human_approval_required)

    def test_multiple_actions_all_hardened(self):
        rec = ActionRecommendation(
            summary="Multi-action proposal", confidence=0.6,
            proposed_actions=[
                ProposedAction(action="Change set-point", action_class="informational",
                               approval_status="not_required"),
                ProposedAction(action="Adjust valve", action_class="process_change",
                               approval_status="approved"),
            ],
        )
        hardened = _harden_process_change_recommendation(rec)
        for action in hardened.proposed_actions:
            self.assertEqual(action.action_class, "process_change")
            self.assertEqual(action.approval_status, "required")
        self.assertTrue(hardened.human_approval_required)


class OptimizationNodeTests(unittest.TestCase):
    def test_no_equipment_tag_refuses(self):
        with patch("app.agents.nodes.optimization.invoke_tool", return_value=({"results": [], "warnings": []}, [])):
            update = optimization_node({"query": "optimize the process", "route": "process_optimization"},
                                        gateway=MagicMock(), session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S5")
        self.assertIn("equipment tag", update["agent_result"]["output"]["reason"].lower())

    def test_no_evidence_refuses(self):
        with patch("app.agents.nodes.optimization.invoke_tool", return_value=({"results": [], "warnings": []}, [])):
            update = optimization_node({"query": "optimize P-204", "route": "process_optimization"},
                                        gateway=MagicMock(), session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S5")
        self.assertIn("documentation", update["agent_result"]["output"]["reason"].lower())

    def test_valid_proposal_is_hardened_before_emitting(self):
        ref = _doc_ref()
        rec = _proposal(ref.evidence_id, action_class="inspection", approval_status="not_required")
        gateway = MagicMock()
        gateway.generate_structured.return_value = _gen_result(rec)
        doc_payload = {"results": [{"evidence_id": ref.evidence_id, "score": 1.0}], "warnings": []}
        latest_payload = {"readings": [], "warnings": []}
        hist_payload = {"records": [], "warnings": []}
        with patch("app.agents.nodes.optimization.invoke_tool",
                   side_effect=[(doc_payload, [ref]), (latest_payload, []),
                                (hist_payload, [])]):
            update = optimization_node({"query": "optimize P-204", "route": "process_optimization"},
                                        gateway=gateway, session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S7")
        output = update["agent_result"]["output"]
        self.assertEqual(output["proposed_actions"][0]["action_class"], "process_change")
        self.assertEqual(output["proposed_actions"][0]["approval_status"], "required")
        self.assertTrue(output["human_approval_required"])
        self.assertEqual(update["action_class"], "process_change")

    def test_authorization_language_triggers_one_regeneration(self):
        ref = _doc_ref()
        bad = _proposal(ref.evidence_id, summary="You are authorized to adjust the set-point.")
        good = _proposal(ref.evidence_id, summary="SOP recommends a set-point adjustment.")
        gateway = MagicMock()
        gateway.generate_structured.side_effect = [_gen_result(bad), _gen_result(good)]
        doc_payload = {"results": [{"evidence_id": ref.evidence_id, "score": 1.0}], "warnings": []}
        latest_payload = {"readings": [], "warnings": []}
        hist_payload = {"records": [], "warnings": []}
        with patch("app.agents.nodes.optimization.invoke_tool",
                   side_effect=[(doc_payload, [ref]), (latest_payload, []),
                                (hist_payload, [])]):
            update = optimization_node({"query": "optimize P-204", "route": "process_optimization"},
                                        gateway=gateway, session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S7")
        self.assertEqual(gateway.generate_structured.call_count, 2)
        self.assertIn("SOP", update["agent_result"]["output"]["summary"])

    def test_confounder_fixture_validates_multiple_trends_acknowledged(self):
        """4F's confounder acknowledgement is prompt-enforced: the agent must
        surface both trends when two variables move together. This test passes
        a fixture where differential pressure and flow both rise, and asserts
        that the response mentions both."""
        ref = _doc_ref(quote="Flow optimization for P-204; pressure ranges 40-60 psi.")
        # Response that mentions both trends: this is what we want.
        good = ActionRecommendation(
            summary="Both differential pressure and flow have increased over the past week. "
                    "This co-movement suggests they may be driven by the same underlying factor "
                    "(e.g., higher throughput). Recommend reviewing whether the current set-points "
                    "remain optimal.",
            confidence=0.7,
            citations=[Citation(evidence_id=ref.evidence_id, locator="page 5", claim="c")],
            proposed_actions=[ProposedAction(action="Review set-point optimization",
                                             action_class="process_change",
                                             approval_status="required")],
        )
        gateway = MagicMock()
        gateway.generate_structured.return_value = _gen_result(good)
        doc_payload = {"results": [{"evidence_id": ref.evidence_id, "score": 1.0}], "warnings": []}
        latest_payload = {"readings": [], "warnings": []}
        hist_payload = {"records": [], "warnings": []}
        with patch("app.agents.nodes.optimization.invoke_tool",
                   side_effect=[(doc_payload, [ref]), (latest_payload, []),
                                (hist_payload, [])]):
            update = optimization_node({"query": "optimize P-204 pressure and flow", "route": "process_optimization"},
                                        gateway=gateway, session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S7")
        summary = update["agent_result"]["output"]["summary"]
        # The response must mention both the pressure trend and the flow trend.
        self.assertIn("pressure", summary.lower())
        self.assertIn("flow", summary.lower())
        # It should acknowledge that they move together.
        self.assertIn("co-movement", summary.lower())


if __name__ == "__main__":
    unittest.main()
