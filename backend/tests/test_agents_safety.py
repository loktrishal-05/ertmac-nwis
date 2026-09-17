"""Phase 4D tests: the authorisation-language validator, the combined
citation+language enforcement loop, and the safety & incident agent node
(including its combined_safety_maintenance behaviour). Fake gateway and
mocked/fake session only -- no live Ollama, Postgres, or Qdrant."""
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.agents.enforcement import EnforcementFailure, enforce_citations_and_authorization_language
from app.agents.evidence import csv_row_evidence, document_chunk_evidence
from app.agents.nodes.safety import _dominant_action_class, _harden_action_recommendation, safety_node
from app.agents.safety_language import contains_authorization_language, find_authorization_language
from app.schemas.agent_outputs import ActionRecommendation, Citation, ProposedAction
from app.services.model_gateway import StructuredOutputError
from app.services.model_gateway.types import GenerationResult, GenerationTimings, GenerationUsage, StructuredResult

SHA = "a" * 64


def _doc_ref(quote="Follow SOP 5.1 for isolation."):
    return document_chunk_evidence(
        chunk_id="c1", document_id=uuid4(), document_version_id=uuid4(), source_filename="sop.pdf",
        source_sha256=SHA, section_path=["5"], page_start=5, page_end=5, bounding_boxes=[], quote=quote,
    )


def _csv_ref(row_number=1):
    return csv_row_evidence(source_filename="f.csv", source_sha256=SHA, source_row_number=row_number)


def _gen_result(value):
    gen = GenerationResult(text="{}", finish_reason="stop", model="m", runtime="ollama",
                            usage=GenerationUsage(), timings=GenerationTimings())
    return StructuredResult(value=value, result=gen)


def _recommendation(evidence_id, summary="Proposal", action_class="informational",
                     approval_status="not_required", human_approval_required=False):
    return ActionRecommendation(
        summary=summary, confidence=0.7, human_approval_required=human_approval_required,
        citations=[Citation(evidence_id=evidence_id, locator="page 5", claim="c")],
        proposed_actions=[ProposedAction(action="Review isolation SOP 5.1", action_class=action_class,
                                          approval_status=approval_status)],
    )


class SafetyLanguageTests(unittest.TestCase):
    def test_clean_text_has_no_violations(self):
        self.assertEqual(find_authorization_language("Per SOP 5.1, isolation requires two valves closed."), [])
        self.assertFalse(contains_authorization_language("Per SOP 5.1, isolation requires two valves closed."))

    def test_you_are_cleared_to_is_flagged(self):
        self.assertTrue(contains_authorization_language("You are cleared to proceed with isolation."))

    def test_permission_granted_is_flagged(self):
        self.assertTrue(contains_authorization_language("Permission is granted to enter the confined space."))

    def test_you_may_now_isolate_is_flagged(self):
        self.assertTrue(contains_authorization_language("You may now isolate the pump."))

    def test_authorised_to_is_flagged(self):
        self.assertTrue(contains_authorization_language("You are authorised to open the valve."))

    def test_permit_issued_is_flagged(self):
        self.assertTrue(contains_authorization_language("The permit has been issued for this work."))

    def test_go_ahead_and_is_flagged(self):
        self.assertTrue(contains_authorization_language("Go ahead and shut down the unit."))

    def test_citing_what_a_procedure_requires_is_not_flagged(self):
        # Reporting a requirement is not granting it.
        text = "SOP 5.1 states that a permit must be obtained before isolation may begin."
        self.assertFalse(contains_authorization_language(text))


class EnforceCitationsAndLanguageTests(unittest.TestCase):
    def test_valid_on_first_attempt(self):
        ref = _doc_ref()
        generate = MagicMock(side_effect=[_recommendation(ref.evidence_id)])
        result = enforce_citations_and_authorization_language(
            generate=generate, extract_citations=lambda r: r.citations,
            extract_language_text=lambda r: r.summary, available=[ref],
        )
        self.assertEqual(result.citations[0].evidence_id, ref.evidence_id)
        generate.assert_called_once_with(None)

    def test_authorization_language_alone_triggers_one_regeneration(self):
        ref = _doc_ref()
        bad = _recommendation(ref.evidence_id, summary="You are cleared to proceed.")
        good = _recommendation(ref.evidence_id, summary="SOP 5.1 requires isolation before entry.")
        generate = MagicMock(side_effect=[bad, good])
        result = enforce_citations_and_authorization_language(
            generate=generate, extract_citations=lambda r: r.citations,
            extract_language_text=lambda r: r.summary, available=[ref],
        )
        self.assertEqual(result.summary, good.summary)
        self.assertEqual(generate.call_count, 2)
        self.assertIn("authoris", generate.call_args_list[1].args[0].lower())

    def test_both_citation_and_language_failures_reported_together(self):
        bad = _recommendation("unknown_id", summary="You are cleared to proceed.")
        generate = MagicMock(side_effect=[bad, bad])
        with self.assertRaises(EnforcementFailure) as ctx:
            enforce_citations_and_authorization_language(
                generate=generate, extract_citations=lambda r: r.citations,
                extract_language_text=lambda r: r.summary, available=[],
            )
        refusal = ctx.exception.refusal
        self.assertIn("unknown_id", str(refusal.missing_evidence))
        self.assertIn("authorisation-implying", refusal.reason)


class HardenActionRecommendationTests(unittest.TestCase):
    def test_approved_is_downgraded_to_required(self):
        rec = _recommendation("e1", action_class="isolation", approval_status="approved")
        hardened = _harden_action_recommendation(rec)
        self.assertEqual(hardened.proposed_actions[0].approval_status, "required")

    def test_non_informational_action_forces_human_approval_required_true(self):
        rec = _recommendation("e1", action_class="shutdown", approval_status="not_required",
                               human_approval_required=False)
        hardened = _harden_action_recommendation(rec)
        self.assertTrue(hardened.human_approval_required)
        self.assertEqual(hardened.proposed_actions[0].approval_status, "required")

    def test_informational_only_action_is_left_alone(self):
        rec = _recommendation("e1", action_class="informational", approval_status="not_required",
                               human_approval_required=False)
        hardened = _harden_action_recommendation(rec)
        self.assertFalse(hardened.human_approval_required)
        self.assertEqual(hardened.proposed_actions[0].approval_status, "not_required")

    def test_dominant_action_class_prefers_most_severe(self):
        rec = ActionRecommendation(
            summary="s", confidence=0.5,
            proposed_actions=[
                ProposedAction(action="a", action_class="informational", approval_status="not_required"),
                ProposedAction(action="b", action_class="shutdown", approval_status="required"),
                ProposedAction(action="c", action_class="inspection", approval_status="required"),
            ],
        )
        self.assertEqual(_dominant_action_class(rec), "shutdown")

    def test_dominant_action_class_none_when_no_actions(self):
        rec = ActionRecommendation(summary="s", confidence=0.5)
        self.assertIsNone(_dominant_action_class(rec))


class SafetyNodeTests(unittest.TestCase):
    def test_no_evidence_refuses_and_directs_to_human_escalation(self):
        with patch("app.agents.nodes.safety.invoke_tool", return_value=({"results": [], "warnings": []}, [])):
            update = safety_node({"query": "gas smell near P-204", "route": "safety"},
                                  gateway=MagicMock(), session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S5")
        self.assertIn("Escalate", update["agent_result"]["output"]["safe_next_step"])

    def test_valid_recommendation_is_emitted_as_s7_with_state_level_fields(self):
        ref = _doc_ref()
        rec = _recommendation(ref.evidence_id, action_class="isolation", approval_status="required",
                               human_approval_required=True)
        gateway = MagicMock()
        gateway.generate_structured.return_value = _gen_result(rec)
        payload = {"results": [{"evidence_id": ref.evidence_id, "score": 1.0}], "warnings": []}
        with patch("app.agents.nodes.safety.invoke_tool", return_value=(payload, [ref])):
            update = safety_node({"query": "isolation guidance for P-204", "route": "safety"},
                                  gateway=gateway, session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S7")
        self.assertTrue(update["human_approval_required"])
        self.assertEqual(update["action_class"], "isolation")

    def test_model_self_approval_is_overridden_before_leaving_the_node(self):
        ref = _doc_ref()
        rec = _recommendation(ref.evidence_id, action_class="shutdown", approval_status="approved")
        gateway = MagicMock()
        gateway.generate_structured.return_value = _gen_result(rec)
        payload = {"results": [{"evidence_id": ref.evidence_id, "score": 1.0}], "warnings": []}
        with patch("app.agents.nodes.safety.invoke_tool", return_value=(payload, [ref])):
            update = safety_node({"query": "shutdown guidance for P-204", "route": "safety"},
                                  gateway=gateway, session=MagicMock())
        output = update["agent_result"]["output"]
        self.assertEqual(output["proposed_actions"][0]["approval_status"], "required")
        self.assertTrue(output["human_approval_required"])

    def test_persistent_authorization_language_refuses_never_ships_the_recommendation(self):
        ref = _doc_ref()
        bad = _recommendation(ref.evidence_id, summary="You are cleared to proceed with isolation.")
        gateway = MagicMock()
        gateway.generate_structured.return_value = _gen_result(bad)
        payload = {"results": [{"evidence_id": ref.evidence_id, "score": 1.0}], "warnings": []}
        with patch("app.agents.nodes.safety.invoke_tool", return_value=(payload, [ref])):
            update = safety_node({"query": "isolation guidance for P-204", "route": "safety"},
                                  gateway=gateway, session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S5")
        self.assertEqual(gateway.generate_structured.call_count, 2)
        self.assertNotIn("cleared", str(update["agent_result"]))

    def test_structured_output_error_refuses_instead_of_propagating(self):
        ref = _doc_ref()
        gateway = MagicMock()
        gateway.generate_structured.side_effect = StructuredOutputError("bad output")
        payload = {"results": [{"evidence_id": ref.evidence_id, "score": 1.0}], "warnings": []}
        with patch("app.agents.nodes.safety.invoke_tool", return_value=(payload, [ref])):
            update = safety_node({"query": "q", "route": "safety"}, gateway=gateway, session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S5")

    def test_combined_route_pulls_maintenance_and_sensor_evidence_for_detected_tag(self):
        doc_ref = _doc_ref()
        maint_ref = _csv_ref(1)
        sensor_ref = _csv_ref(2)
        rec = _recommendation(doc_ref.evidence_id)
        gateway = MagicMock()
        gateway.generate_structured.return_value = _gen_result(rec)

        calls = []

        def fake_invoke_tool(name, session, arguments):
            calls.append((name, arguments))
            if name == "retrieve_documents":
                return ({"results": [{"evidence_id": doc_ref.evidence_id, "score": 1.0}], "warnings": []}, [doc_ref])
            if name == "get_maintenance_history":
                row = {"evidence_id": maint_ref.evidence_id, "equipment_tag": arguments["equipment_tag"]}
                return ({"records": [row]}, [maint_ref])
            if name == "get_latest_reading":
                row = {"evidence_id": sensor_ref.evidence_id, "equipment_tag": arguments["equipment_tag"]}
                return ({"readings": [row]}, [sensor_ref])
            raise AssertionError(f"unexpected tool {name}")

        with patch("app.agents.nodes.safety.invoke_tool", side_effect=fake_invoke_tool):
            update = safety_node(
                {"query": "P-204 shows a safety alarm and an overdue work order", "route": "combined_safety_maintenance"},
                gateway=gateway, session=MagicMock(),
            )
        called_tools = {name for name, _ in calls}
        self.assertEqual(called_tools, {"retrieve_documents", "get_maintenance_history", "get_latest_reading"})
        self.assertEqual(len(update["evidence"]), 3)

    def test_pure_safety_route_never_calls_maintenance_or_sensor_tools(self):
        doc_ref = _doc_ref()
        rec = _recommendation(doc_ref.evidence_id)
        gateway = MagicMock()
        gateway.generate_structured.return_value = _gen_result(rec)
        payload = {"results": [{"evidence_id": doc_ref.evidence_id, "score": 1.0}], "warnings": []}
        with patch("app.agents.nodes.safety.invoke_tool", return_value=(payload, [doc_ref])) as mocked:
            safety_node({"query": "gas alarm at P-204", "route": "safety"}, gateway=gateway, session=MagicMock())
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[0], "retrieve_documents")


class SafetyGraphWiringTests(unittest.TestCase):
    def _fake_gateway(self, route):
        from app.agents.nodes.router import RouteDecision
        decision = RouteDecision(route=route, confidence=0.9, reasoning="r")
        return MagicMock(generate_structured=MagicMock(return_value=_gen_result(decision)))

    def _invoke(self, route):
        from app.agents.graph import build_graph
        from app.core.config import settings as cfg
        with patch("app.agents.graph.get_model_gateway", return_value=self._fake_gateway(route)), \
             patch("app.agents.nodes.safety.invoke_tool", return_value=({"results": [], "warnings": []}, [])):
            graph = build_graph(session=MagicMock())
            # invoke_tool is looked up at call time inside safety_node, not captured by
            # closure the way `gateway` is -- the patch must still be active here.
            return graph.invoke({
                "run_id": "r", "query": "q", "route": None, "route_confidence": None, "route_reasoning": None,
                "evidence": [], "tool_invocations": [], "agent_result": None, "warnings": [], "errors": [],
                "human_approval_required": False, "action_class": None, "started_at": "x", "finished_at": None,
                "step_records": [],
            }, config={"recursion_limit": cfg.agent_max_steps})

    def test_safety_route_no_longer_reports_not_implemented(self):
        state = self._invoke("safety")
        self.assertEqual(state["agent_result"]["schema"], "S5")

    def test_combined_safety_maintenance_route_no_longer_reports_not_implemented(self):
        state = self._invoke("combined_safety_maintenance")
        self.assertEqual(state["agent_result"]["schema"], "S5")


if __name__ == "__main__":
    unittest.main()
