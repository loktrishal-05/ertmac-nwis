"""Phase 4E tests: the asymmetric diagnostic-language validator, the
combined citation+diagnostic-language enforcement loop, the deterministic
threshold-numeral extractor, and the maintenance & asset reliability agent
node (both the S4 general-assessment path and the S6 threshold-loop path).
Fake gateway and mocked/fake session only -- no live Ollama, Postgres, or
Qdrant."""
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.agents.enforcement import EnforcementFailure, enforce_citations_and_diagnostic_language
from app.agents.evidence import csv_row_evidence, document_chunk_evidence
from app.agents.nodes.maintenance import _anomaly_status, _extract_threshold, maintenance_node
from app.agents.observation_language import contains_diagnostic_language, find_diagnostic_language
from app.schemas.agent_outputs import Citation, MaintenanceAssessment, MaintenanceHypothesis, SensorInterpretation
from app.services.model_gateway import StructuredOutputError
from app.services.model_gateway.types import GenerationResult, GenerationTimings, GenerationUsage, StructuredResult

SHA = "a" * 64


def _doc_ref(quote="Vibration must not exceed a maximum of 4.5 mm/s during normal operation."):
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


def _assessment(evidence_id, observations=("The unit was inspected on schedule.",)):
    return MaintenanceAssessment(
        asset_tag="P-204", observations=list(observations), overall_confidence=0.7,
        citations=[Citation(evidence_id=evidence_id, locator="row 1", claim="c")],
        hypotheses=[MaintenanceHypothesis(text="Possible bearing wear", supporting_evidence=[evidence_id], confidence=0.4)],
    )


def _interpretation(asset_tag="WRONG-TAG", anomaly_status="normal"):
    return SensorInterpretation(asset_tag=asset_tag, time_window="model's own guess", anomaly_status=anomaly_status,
                                 confidence=0.6)


class ObservationLanguageTests(unittest.TestCase):
    def test_clean_factual_text_has_no_violations(self):
        text = "Vibration reading was 4.2 mm/s at 09:00, within the recorded range."
        self.assertEqual(find_diagnostic_language(text), [])
        self.assertFalse(contains_diagnostic_language(text))

    def test_each_forbidden_word_is_flagged_in_observations_context(self):
        for word, sentence in [
            ("bearing", "The bearing was inspected."),
            ("failure", "No failure was recorded."),
            ("damage", "Visible damage was noted."),
            ("cavitation", "Cavitation was suspected."),
            ("diagnos", "A diagnosis was made."),
            ("impeller", "The impeller was checked."),
        ]:
            with self.subTest(word=word):
                self.assertTrue(contains_diagnostic_language(sentence))

    def test_hypotheses_style_text_is_still_flagged_by_the_bare_function(self):
        # The asymmetry is enforced by WHERE this function is applied (observations
        # only, never hypotheses), not by the function itself being context-aware.
        self.assertTrue(contains_diagnostic_language("Hypothesis: bearing failure is likely."))


class EnforceCitationsAndDiagnosticLanguageTests(unittest.TestCase):
    def test_valid_on_first_attempt(self):
        ref = _csv_ref()
        generate = MagicMock(side_effect=[_assessment(ref.evidence_id)])
        result = enforce_citations_and_diagnostic_language(
            generate=generate, extract_citations=lambda a: a.citations,
            extract_observation_text=lambda a: " ".join(a.observations), available=[ref],
        )
        self.assertEqual(result.citations[0].evidence_id, ref.evidence_id)
        generate.assert_called_once_with(None)

    def test_diagnostic_word_in_observations_triggers_one_regeneration(self):
        ref = _csv_ref()
        bad = _assessment(ref.evidence_id, observations=["Likely bearing failure detected."])
        good = _assessment(ref.evidence_id, observations=["Vibration reading was elevated at 09:00."])
        generate = MagicMock(side_effect=[bad, good])
        result = enforce_citations_and_diagnostic_language(
            generate=generate, extract_citations=lambda a: a.citations,
            extract_observation_text=lambda a: " ".join(a.observations), available=[ref],
        )
        self.assertEqual(result.observations, good.observations)
        self.assertEqual(generate.call_count, 2)
        self.assertIn("diagnostic", generate.call_args_list[1].args[0].lower())

    def test_persistent_violation_raises_and_never_returns_the_bad_assessment(self):
        ref = _csv_ref()
        bad = _assessment(ref.evidence_id, observations=["Likely bearing failure detected."])
        generate = MagicMock(side_effect=[bad, bad])
        with self.assertRaises(EnforcementFailure) as ctx:
            enforce_citations_and_diagnostic_language(
                generate=generate, extract_citations=lambda a: a.citations,
                extract_observation_text=lambda a: " ".join(a.observations), available=[ref],
            )
        self.assertIn("failure mode", ctx.exception.refusal.reason)


class ExtractThresholdTests(unittest.TestCase):
    def test_maximum_of_phrasing_is_extracted(self):
        ref = _doc_ref("Vibration must not exceed a maximum of 4.5 mm/s during normal operation.")
        found_ref, value = _extract_threshold([ref])
        self.assertIs(found_ref, ref)
        self.assertEqual(value, 4.5)

    def test_threshold_is_phrasing_is_extracted(self):
        ref = _doc_ref("The bearing temperature threshold is 85 degrees.")
        _, value = _extract_threshold([ref])
        self.assertEqual(value, 85.0)

    def test_shall_not_exceed_phrasing_is_extracted(self):
        ref = _doc_ref("Discharge pressure shall not exceed 120 psi at any time.")
        _, value = _extract_threshold([ref])
        self.assertEqual(value, 120.0)

    def test_no_numeral_returns_none_none(self):
        ref = _doc_ref("Inspect the pump housing annually for corrosion.")
        found_ref, value = _extract_threshold([ref])
        self.assertIsNone(found_ref)
        self.assertIsNone(value)

    def test_first_matching_ref_wins_when_multiple_are_present(self):
        clean = _doc_ref("General inspection notes with no numeric limit.")
        limited = _doc_ref("Maximum value: 10.")
        found_ref, value = _extract_threshold([clean, limited])
        self.assertIs(found_ref, limited)
        self.assertEqual(value, 10.0)


class AnomalyStatusTests(unittest.TestCase):
    def test_threshold_exceeded_is_critical(self):
        self.assertEqual(_anomaly_status([{"kind": "threshold_exceeded"}]), "critical")

    def test_sudden_change_is_warning(self):
        self.assertEqual(_anomaly_status([{"kind": "sudden_change"}]), "warning")

    def test_no_observations_is_normal(self):
        self.assertEqual(_anomaly_status([]), "normal")

    def test_critical_wins_over_warning_when_both_present(self):
        self.assertEqual(_anomaly_status([{"kind": "bad_quality"}, {"kind": "threshold_below"}]), "critical")


class MaintenanceNodeTests(unittest.TestCase):
    def test_no_equipment_tag_refuses(self):
        update = maintenance_node({"query": "how is the pump doing"}, gateway=MagicMock(), session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S5")

    def test_no_evidence_at_all_refuses(self):
        with patch("app.agents.nodes.maintenance.invoke_tool", return_value=({"results": [], "warnings": [],
                                                                                "records": [], "readings": []}, [])):
            update = maintenance_node({"query": "status of P-204"}, gateway=MagicMock(), session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S5")

    def test_sop_without_numeral_falls_back_to_s4_never_calls_compute_sensor_features(self):
        sop_ref = _doc_ref("Inspect the pump housing annually for corrosion.")
        hist_ref = _csv_ref(1)
        reading_ref = _csv_ref(2)
        assessment = _assessment(sop_ref.evidence_id)
        gateway = MagicMock()
        gateway.generate_structured.return_value = _gen_result(assessment)

        def fake_invoke_tool(name, session, arguments):
            if name == "retrieve_documents":
                return ({"results": [{"evidence_id": sop_ref.evidence_id, "score": 1.0}], "warnings": []}, [sop_ref])
            if name == "get_maintenance_history":
                return ({"records": [{"evidence_id": hist_ref.evidence_id}]}, [hist_ref])
            if name == "get_latest_reading":
                return ({"readings": [{"evidence_id": reading_ref.evidence_id, "sensor_tag": "VIB-1"}]}, [reading_ref])
            raise AssertionError(f"compute_sensor_features must not be called: {name}")

        with patch("app.agents.nodes.maintenance.invoke_tool", side_effect=fake_invoke_tool):
            update = maintenance_node({"query": "status of P-204"}, gateway=gateway, session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S4")

    def test_no_sensor_reading_falls_back_to_s4_never_calls_compute_sensor_features(self):
        sop_ref = _doc_ref()  # has a numeral
        hist_ref = _csv_ref(1)
        assessment = _assessment(sop_ref.evidence_id)
        gateway = MagicMock()
        gateway.generate_structured.return_value = _gen_result(assessment)

        def fake_invoke_tool(name, session, arguments):
            if name == "retrieve_documents":
                return ({"results": [{"evidence_id": sop_ref.evidence_id, "score": 1.0}], "warnings": []}, [sop_ref])
            if name == "get_maintenance_history":
                return ({"records": [{"evidence_id": hist_ref.evidence_id}]}, [hist_ref])
            if name == "get_latest_reading":
                return ({"readings": []}, [])
            raise AssertionError(f"compute_sensor_features must not be called: {name}")

        with patch("app.agents.nodes.maintenance.invoke_tool", side_effect=fake_invoke_tool):
            update = maintenance_node({"query": "status of P-204"}, gateway=gateway, session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S4")

    def test_threshold_loop_produces_s6_with_two_citations_and_deterministic_fields(self):
        sop_ref = _doc_ref("Vibration must not exceed a maximum of 4.5 mm/s during normal operation.")
        hist_ref = _csv_ref(1)
        reading_ref = _csv_ref(2)
        sensor_ref = _csv_ref(3)
        # The model's own asset_tag/time_window/anomaly_status must be overridden.
        model_output = _interpretation(asset_tag="WRONG-TAG", anomaly_status="normal")
        gateway = MagicMock()
        gateway.generate_structured.return_value = _gen_result(model_output)

        raw_observations = [{
            "kind": "threshold_exceeded",
            "observation": "vibration value 5.1 mm/s exceeded configured maximum 4.5 at 2026-01-01T00:00:00+00:00",
            "evidence": {"value": 5.1, "threshold": 4.5},
        }]

        def fake_invoke_tool(name, session, arguments):
            if name == "retrieve_documents":
                return ({"results": [{"evidence_id": sop_ref.evidence_id, "score": 1.0}], "warnings": []}, [sop_ref])
            if name == "get_maintenance_history":
                return ({"records": [{"evidence_id": hist_ref.evidence_id}]}, [hist_ref])
            if name == "get_latest_reading":
                return ({"readings": [{"evidence_id": reading_ref.evidence_id, "sensor_tag": "VIB-1"}]}, [reading_ref])
            if name == "compute_sensor_features":
                self.assertEqual(arguments["thresholds"], {"maximum": 4.5})
                return ({
                    "measurement": "vibration", "window_start": "2026-01-01T00:00:00+00:00",
                    "window_end": "2026-01-08T00:00:00+00:00", "observations": raw_observations,
                    "evidence_id": sensor_ref.evidence_id,
                }, [sensor_ref])
            raise AssertionError(f"unexpected tool {name}")

        with patch("app.agents.nodes.maintenance.invoke_tool", side_effect=fake_invoke_tool):
            update = maintenance_node({"query": "is P-204 vibration ok"}, gateway=gateway, session=MagicMock())

        self.assertEqual(update["agent_result"]["schema"], "S6")
        output = update["agent_result"]["output"]
        self.assertEqual(output["asset_tag"], "P-204")
        self.assertEqual(output["anomaly_status"], "critical")
        cited_ids = {c["evidence_id"] for c in output["citations"]}
        self.assertEqual(cited_ids, {sop_ref.evidence_id, sensor_ref.evidence_id})
        self.assertEqual(len(output["observations"]), 1)
        self.assertEqual(output["observations"][0]["evidence_id"], sensor_ref.evidence_id)
        self.assertNotIn("bearing", str(output).lower())  # the observation text is purely factual

    def test_threshold_loop_falls_back_to_s4_when_nothing_crosses_the_threshold(self):
        sop_ref = _doc_ref("Vibration must not exceed a maximum of 4.5 mm/s during normal operation.")
        hist_ref = _csv_ref(1)
        reading_ref = _csv_ref(2)
        assessment = _assessment(sop_ref.evidence_id)
        gateway = MagicMock()
        gateway.generate_structured.return_value = _gen_result(assessment)

        def fake_invoke_tool(name, session, arguments):
            if name == "retrieve_documents":
                return ({"results": [{"evidence_id": sop_ref.evidence_id, "score": 1.0}], "warnings": []}, [sop_ref])
            if name == "get_maintenance_history":
                return ({"records": [{"evidence_id": hist_ref.evidence_id}]}, [hist_ref])
            if name == "get_latest_reading":
                return ({"readings": [{"evidence_id": reading_ref.evidence_id, "sensor_tag": "VIB-1"}]}, [reading_ref])
            if name == "compute_sensor_features":
                return ({"measurement": "vibration", "window_start": "x", "window_end": "y", "observations": []}, [])
            raise AssertionError(f"unexpected tool {name}")

        with patch("app.agents.nodes.maintenance.invoke_tool", side_effect=fake_invoke_tool):
            update = maintenance_node({"query": "is P-204 vibration ok"}, gateway=gateway, session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S4")

    def test_structured_output_error_on_s4_path_refuses_instead_of_propagating(self):
        sop_ref = _doc_ref("General inspection notes with no numeric limit.")
        hist_ref = _csv_ref(1)
        gateway = MagicMock()
        gateway.generate_structured.side_effect = StructuredOutputError("bad output")

        def fake_invoke_tool(name, session, arguments):
            if name == "retrieve_documents":
                return ({"results": [{"evidence_id": sop_ref.evidence_id, "score": 1.0}], "warnings": []}, [sop_ref])
            if name == "get_maintenance_history":
                return ({"records": [{"evidence_id": hist_ref.evidence_id}]}, [hist_ref])
            if name == "get_latest_reading":
                return ({"readings": []}, [])
            raise AssertionError(name)

        with patch("app.agents.nodes.maintenance.invoke_tool", side_effect=fake_invoke_tool):
            update = maintenance_node({"query": "status of P-204"}, gateway=gateway, session=MagicMock())
        self.assertEqual(update["agent_result"]["schema"], "S5")


class MaintenanceGraphWiringTests(unittest.TestCase):
    def test_maintenance_route_no_longer_reports_not_implemented(self):
        from app.agents.graph import build_graph
        from app.agents.nodes.router import RouteDecision
        from app.core.config import settings as cfg
        decision = RouteDecision(route="maintenance", confidence=0.9, reasoning="r")
        gateway = MagicMock(generate_structured=MagicMock(return_value=_gen_result(decision)))
        with patch("app.agents.graph.get_model_gateway", return_value=gateway), \
             patch("app.agents.nodes.maintenance.invoke_tool",
                   return_value=({"results": [], "warnings": [], "records": [], "readings": []}, [])):
            graph = build_graph(session=MagicMock())
            state = graph.invoke({
                "run_id": "r", "query": "status of P-204", "route": None, "route_confidence": None,
                "route_reasoning": None, "evidence": [], "tool_invocations": [], "agent_result": None,
                "warnings": [], "errors": [], "human_approval_required": False, "action_class": None,
                "started_at": "x", "finished_at": None, "step_records": [],
            }, config={"recursion_limit": cfg.agent_max_steps})
        self.assertEqual(state["agent_result"]["schema"], "S5")


if __name__ == "__main__":
    unittest.main()
