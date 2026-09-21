"""Phase 4B agent-orchestration tests. Fake gateway only (no live Ollama call);
tool adapters are tested against mocked Phase 3A/3B1/3B2/3C service functions
or an in-memory fake session, never a live DB. Live validation of the real
graph against real services is smoke_agents.py's job, not this file's."""
import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.agents.citations import validate_citations
from app.agents.evidence import (
    csv_row_evidence,
    document_chunk_evidence,
    make_evidence_id,
    pid_region_evidence,
    sensor_window_evidence,
)
from app.agents.graph import build_graph, get_graph, run_graph
from app.agents.nodes.router import RouteDecision, router_node
from app.agents.nodes.stubs import SUB_PHASE, make_stub_node
from app.agents.prompts.router import ROUTE_NAMES, ROUTES, ROUTER_SYSTEM_PROMPT
from app.agents.registry import (
    ToolArgumentError,
    ToolNotFoundError,
    get_tool,
    invoke_tool,
    list_tools,
    register,
)
from app.agents.tools.base import clamp_limit, clamp_window
from app.agents.tracing import record_run
from app.core.config import Settings, settings
from app.db.models.agent_run import AgentRun
from app.db.models.agent_run_step import AgentRunStep
from app.db.models.document_version import DocumentVersion
from app.main import app
from app.schemas.knowledge import BoundingBox, Citation, RetrievedChunk, RetrieveResponse
from app.schemas.structured import (
    MaintenanceRecordOut,
    SensorFeatureResponse,
    SensorFeatureSummary,
    SensorReadingOut,
    StructuredCitation,
)
from app.services.model_gateway import StructuredOutputError
from app.services.model_gateway.types import GenerationResult, GenerationTimings, GenerationUsage, StructuredResult

AGENTS_PACKAGE_DIR = Path(__file__).resolve().parents[1] / "app" / "agents"
SHA = "a" * 64


class EvidenceTests(unittest.TestCase):
    def test_evidence_id_is_deterministic_and_sha256_derived(self):
        first = make_evidence_id("csv_row", SHA, "5")
        second = make_evidence_id("csv_row", SHA, "5")
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("csv_row_"))

    def test_evidence_id_changes_with_any_input(self):
        base = make_evidence_id("csv_row", SHA, "5")
        self.assertNotEqual(base, make_evidence_id("sensor_window", SHA, "5"))
        self.assertNotEqual(base, make_evidence_id("csv_row", "b" * 64, "5"))
        self.assertNotEqual(base, make_evidence_id("csv_row", SHA, "6"))

    def test_shared_locator_does_not_collide_across_distinct_chunks(self):
        # Two distinct chunks reported as "page 3" must not collide: the id is
        # derived from chunk_id, not the human-readable locator.
        common = dict(document_id=uuid4(), document_version_id=uuid4(), source_filename="sop.pdf",
                      source_sha256=SHA, section_path=["A"], page_start=3, page_end=3,
                      bounding_boxes=[], quote="q")
        first = document_chunk_evidence(chunk_id="chunk-a", **common)
        second = document_chunk_evidence(chunk_id="chunk-b", **common)
        self.assertEqual(first.locator, second.locator)
        self.assertNotEqual(first.evidence_id, second.evidence_id)

    def test_document_chunk_evidence_ocr_fields_pass_through(self):
        ref = document_chunk_evidence(
            chunk_id="c1", document_id=uuid4(), document_version_id=uuid4(), source_filename="f.pdf",
            source_sha256=SHA, section_path=[], page_start=1, page_end=2, bounding_boxes=[], quote="q",
            ocr_derived=True, ocr_confidence=0.4, ocr_status="ambiguous",
        )
        self.assertEqual(ref.kind, "document_chunk")
        self.assertEqual(ref.locator, "pages 1-2")
        self.assertEqual(ref.ocr_status, "ambiguous")

    def test_pid_region_evidence_shape(self):
        ref = pid_region_evidence(
            region_id="r1", document_id=uuid4(), document_version_id=uuid4(), source_filename="p.pdf",
            source_sha256=SHA, page=1, bbox=(0.0, 0.0, 1.0, 1.0), confidence=0.9,
            ocr_status="unverified", combined_text="P-204",
        )
        self.assertEqual(ref.kind, "pid_region")
        self.assertIn("region r1", ref.locator)

    def test_csv_row_evidence_shape(self):
        ref = csv_row_evidence(source_filename="f.csv", source_sha256=SHA, source_row_number=7)
        self.assertEqual(ref.kind, "csv_row")
        self.assertEqual(ref.locator, "row 7")
        self.assertEqual(ref.source_row_number, 7)

    def test_sensor_window_evidence_shape(self):
        ref = sensor_window_evidence(source_filename="f.csv", source_sha256=SHA, citation_label="P-204/vibration",
                                      provenance=[{"source_filename": "f.csv"}])
        self.assertEqual(ref.kind, "sensor_window")
        self.assertEqual(ref.locator, "P-204/vibration")

    def test_evidence_models_forbid_extra_fields(self):
        from app.agents.evidence import CSVRowEvidence
        with self.assertRaises(ValidationError):
            CSVRowEvidence(evidence_id="x", source_filename="f", source_sha256=SHA, locator="row 1",
                            source_row_number=1, extra_field="nope")


class CitationValidatorTests(unittest.TestCase):
    def _refs(self, n):
        return [csv_row_evidence(source_filename="f.csv", source_sha256=SHA, source_row_number=i) for i in range(n)]

    def test_all_cited_is_valid(self):
        refs = self._refs(2)
        result = validate_citations(emitted=[r.evidence_id for r in refs], available=refs)
        self.assertTrue(result.valid)
        self.assertEqual(result.unknown_ids, [])
        self.assertEqual(result.uncited_evidence_ids, [])
        self.assertEqual(result.cited_count, 2)
        self.assertEqual(result.available_count, 2)

    def test_unknown_id_marks_invalid(self):
        refs = self._refs(1)
        result = validate_citations(emitted=[refs[0].evidence_id, "csv_row_doesnotexist"], available=refs)
        self.assertFalse(result.valid)
        self.assertEqual(result.unknown_ids, ["csv_row_doesnotexist"])

    def test_uncited_evidence_does_not_invalidate(self):
        refs = self._refs(2)
        result = validate_citations(emitted=[refs[0].evidence_id], available=refs)
        self.assertTrue(result.valid)
        self.assertEqual(result.uncited_evidence_ids, [refs[1].evidence_id])

    def test_empty_emitted_and_available(self):
        result = validate_citations(emitted=[], available=[])
        self.assertTrue(result.valid)
        self.assertEqual(result.cited_count, 0)
        self.assertEqual(result.available_count, 0)


class RegistryTests(unittest.TestCase):
    def test_all_seven_tools_registered_exactly_once(self):
        names = sorted(spec.name for spec in list_tools())
        self.assertEqual(names, sorted([
            "retrieve_documents", "get_pid_regions", "get_maintenance_history", "get_work_order",
            "get_sensor_readings", "get_latest_reading", "compute_sensor_features",
        ]))

    def test_duplicate_registration_raises(self):
        spec = list_tools()[0]
        with self.assertRaises(RuntimeError):
            register(spec, MagicMock(), MagicMock())

    def test_unregistered_tool_raises_tool_not_found(self):
        with self.assertRaises(ToolNotFoundError):
            get_tool("no_such_tool")

    def test_invalid_arguments_raise_tool_argument_error_not_generic_exception(self):
        with self.assertRaises(ToolArgumentError):
            invoke_tool("get_work_order", session=MagicMock(), raw_arguments={"work_order_id": "WO-1", "bogus": 1})

    def test_missing_required_argument_raises_tool_argument_error(self):
        with self.assertRaises(ToolArgumentError):
            invoke_tool("get_work_order", session=MagicMock(), raw_arguments={})

    def test_invoke_tool_calls_the_registered_adapter(self):
        with patch("app.agents.tools.maintenance.work_order_lookup", return_value=[]):
            payload, refs = invoke_tool("get_work_order", session=MagicMock(), raw_arguments={"work_order_id": "WO-1"})
        self.assertEqual(payload, {"found": False, "records": []})
        self.assertEqual(refs, [])


class ToolBaseTests(unittest.TestCase):
    def test_clamp_limit_passes_through_under_cap(self):
        self.assertEqual(clamp_limit(10), 10)

    def test_clamp_limit_caps_at_configured_max(self):
        self.assertEqual(clamp_limit(10 ** 9), settings.structured_query_max_limit)

    def test_clamp_window_passes_through_short_span(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        self.assertEqual(clamp_window(start, end), (start, end))

    def test_clamp_window_caps_long_span_to_configured_max_days(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = start + timedelta(days=settings.agent_tool_max_window_days + 100)
        clamped_start, clamped_end = clamp_window(start, end)
        self.assertEqual(clamped_start, start)
        self.assertEqual(clamped_end - start, timedelta(days=settings.agent_tool_max_window_days))

    def test_clamp_window_passes_through_one_sided_bounds_unbounded(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(clamp_window(start, None), (start, None))
        self.assertEqual(clamp_window(None, None), (None, None))


class KnowledgeToolTests(unittest.TestCase):
    def _chunk(self):
        citation = Citation(
            title="SOP", source_filename="sop.pdf", source_uri="raw/sop.pdf", source_sha256=SHA,
            revision=None, section_path=["1"], page_start=1, page_end=1, quote="Do X.",
            bounding_boxes=[BoundingBox(page=1, coordinates=(0, 0, 1, 1), origin="TOPLEFT")],
        )
        return RetrievedChunk(chunk_id=uuid4(), document_id=uuid4(), document_version_id=uuid4(),
                               score=0.8, content="Do X.", citation=citation)

    def test_retrieve_documents_builds_evidence_and_payload(self):
        from app.agents.tools.knowledge import RetrieveDocumentsArguments, retrieve_documents
        response = RetrieveResponse(strategy="hybrid_rerank", warnings=["w"], query="q",
                                     detected_identifiers={}, results=[self._chunk()])
        with patch("app.agents.tools.knowledge.retrieve", return_value=response) as mocked:
            payload, refs = retrieve_documents(MagicMock(), RetrieveDocumentsArguments(query="q"))
        mocked.assert_called_once()
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].kind, "document_chunk")
        self.assertEqual(payload["strategy"], "hybrid_rerank")
        self.assertEqual(payload["results"][0]["evidence_id"], refs[0].evidence_id)

    def test_get_pid_regions_reports_missing_version_as_warning_not_error(self):
        from app.agents.tools.knowledge import GetPIDRegionsArguments, get_pid_regions
        session = MagicMock()
        session.get.return_value = None
        payload, refs = get_pid_regions(session, GetPIDRegionsArguments(document_version_id=uuid4()))
        self.assertEqual(refs, [])
        self.assertEqual(payload["regions"], [])
        self.assertIn("No processed P&ID", payload["warnings"][0])

    def test_get_pid_regions_reports_non_pid_version_as_warning(self):
        from app.agents.tools.knowledge import GetPIDRegionsArguments, get_pid_regions
        version = DocumentVersion(id=uuid4(), document_id=uuid4(), source_sha256=SHA,
                                   ingestion_metadata={"kind": "document"})
        session = MagicMock()
        session.get.return_value = version
        payload, refs = get_pid_regions(session, GetPIDRegionsArguments(document_version_id=version.id))
        self.assertEqual(refs, [])

    def test_get_pid_regions_reports_missing_manifest_artifact_as_warning(self):
        from app.agents.tools.knowledge import GetPIDRegionsArguments, get_pid_regions
        version = DocumentVersion(id=uuid4(), document_id=uuid4(), source_sha256=SHA,
                                   ingestion_metadata={"kind": "pid"})
        session = MagicMock()
        session.get.return_value = version
        payload, refs = get_pid_regions(session, GetPIDRegionsArguments(document_version_id=version.id))
        self.assertEqual(refs, [])
        self.assertIn("manifest artifact is missing", payload["warnings"][0])


class MaintenanceToolTests(unittest.TestCase):
    def _record(self, row_number=1):
        return MaintenanceRecordOut(
            id=uuid4(), equipment_tag="P-204", raw_equipment_tag="p204", work_order_id="WO-1",
            maintenance_type="preventive", failure_mode=None, maintenance_date=None, description=None,
            downtime_hours=None, parts_replaced=None, technician_notes=None, status="closed",
            ingested_at=datetime.now(timezone.utc),
            citation=StructuredCitation(source_filename="wo.csv", source_sha256=SHA, source_row_number=row_number),
        )

    def test_get_maintenance_history_normalizes_tag_and_clamps_window(self):
        from app.agents.tools.maintenance import GetMaintenanceHistoryArguments, get_maintenance_history
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        end = start + timedelta(days=99999)
        with patch("app.agents.tools.maintenance.maintenance_history", return_value=[self._record()]) as mocked:
            payload, refs = get_maintenance_history(MagicMock(), GetMaintenanceHistoryArguments(
                equipment_tag="p-204", start=start, end=end,
            ))
        called_kwargs = mocked.call_args.kwargs
        self.assertEqual(called_kwargs["equipment_tag"], "P-204")
        self.assertLessEqual(called_kwargs["end"] - called_kwargs["start"], timedelta(days=settings.agent_tool_max_window_days))
        self.assertEqual(len(refs), 1)
        self.assertEqual(payload["records"][0]["evidence_id"], refs[0].evidence_id)

    def test_get_work_order_not_found_is_not_an_error(self):
        from app.agents.tools.maintenance import GetWorkOrderArguments, get_work_order
        with patch("app.agents.tools.maintenance.work_order_lookup", return_value=[]):
            payload, refs = get_work_order(MagicMock(), GetWorkOrderArguments(work_order_id="WO-404"))
        self.assertEqual(payload, {"found": False, "records": []})
        self.assertEqual(refs, [])

    def test_get_work_order_found_returns_evidence(self):
        from app.agents.tools.maintenance import GetWorkOrderArguments, get_work_order
        with patch("app.agents.tools.maintenance.work_order_lookup", return_value=[self._record()]):
            payload, refs = get_work_order(MagicMock(), GetWorkOrderArguments(work_order_id="WO-1"))
        self.assertTrue(payload["found"])
        self.assertEqual(len(refs), 1)


class SensorToolTests(unittest.TestCase):
    def _reading(self, row_number=1):
        return SensorReadingOut(
            id=uuid4(), equipment_tag="P-204", sensor_tag="VIB-1", measurement="vibration", value=1.0,
            unit="mm/s", quality="good", timestamp=datetime.now(timezone.utc), ingested_at=datetime.now(timezone.utc),
            citation=StructuredCitation(source_filename="s.csv", source_sha256=SHA, source_row_number=row_number),
        )

    def test_get_sensor_readings_forwards_measurement_verbatim_not_renamed(self):
        # The critical mapping: `measurement` is passed straight through to
        # sensor_readings_query, which maps it onto SensorReading.sensor_type
        # internally. This adapter must never invent its own mapping.
        from app.agents.tools.sensors import GetSensorReadingsArguments, get_sensor_readings
        with patch("app.agents.tools.sensors.sensor_readings_query", return_value=[self._reading()]) as mocked:
            get_sensor_readings(MagicMock(), GetSensorReadingsArguments(equipment_tag="p-204", measurement="vibration"))
        self.assertEqual(mocked.call_args.kwargs["measurement"], "vibration")
        self.assertEqual(mocked.call_args.kwargs["equipment_tag"], "P-204")

    def test_get_latest_reading_normalizes_tag(self):
        from app.agents.tools.sensors import GetLatestReadingArguments, get_latest_reading
        with patch("app.agents.tools.sensors.sensor_latest", return_value=[self._reading()]) as mocked:
            payload, refs = get_latest_reading(MagicMock(), GetLatestReadingArguments(equipment_tag="p-204"))
        self.assertEqual(mocked.call_args.args[1], "P-204")
        self.assertEqual(len(refs), 1)

    def test_compute_sensor_features_never_invents_a_threshold_default(self):
        from app.agents.tools.sensors import ComputeSensorFeaturesArguments, compute_sensor_features
        response = SensorFeatureResponse(
            equipment_tag="P-204", sensor_tag="VIB-1", measurement="vibration", unit="mm/s",
            window_start=datetime.now(timezone.utc), window_end=datetime.now(timezone.utc) + timedelta(hours=1),
            features=SensorFeatureSummary(count=0), observations=[], citation_label="P-204/VIB-1", provenance=[],
        )
        with patch("app.agents.tools.sensors.sensor_features_query", return_value=response) as mocked:
            payload, refs = compute_sensor_features(MagicMock(), ComputeSensorFeaturesArguments(
                equipment_tag="P-204", sensor_tag="VIB-1",
                start=datetime.now(timezone.utc), end=datetime.now(timezone.utc) + timedelta(hours=1),
            ))
        request = mocked.call_args.args[1]
        self.assertIsNone(request.thresholds.maximum)
        self.assertIsNone(request.thresholds.minimum)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].source_filename, "no_matching_readings")


class RouterNodeTests(unittest.TestCase):
    def _decision_gateway(self, route="knowledge", confidence=0.9, reasoning="r"):
        decision = RouteDecision(route=route, confidence=confidence, reasoning=reasoning)
        gen = GenerationResult(text="{}", finish_reason="stop", model="m", runtime="ollama",
                                usage=GenerationUsage(), timings=GenerationTimings())
        gateway = MagicMock()
        gateway.generate_structured.return_value = StructuredResult(value=decision, result=gen)
        return gateway

    def test_confident_decision_routes_directly(self):
        gateway = self._decision_gateway(route="safety", confidence=0.95)
        update = router_node({"query": "gas leak"}, gateway=gateway)
        self.assertEqual(update["route"], "safety")
        self.assertEqual(update["route_confidence"], 0.95)
        self.assertIn("_usage", update)
        self.assertIn("_timings", update)

    def test_low_confidence_falls_back_to_clarification_with_warning(self):
        gateway = self._decision_gateway(route="knowledge", confidence=0.1)
        update = router_node({"query": "??"}, gateway=gateway)
        self.assertEqual(update["route"], "clarification")
        self.assertTrue(any("confidence" in w for w in update["warnings"]))

    def test_structured_output_error_falls_back_to_clarification(self):
        gateway = MagicMock()
        gateway.generate_structured.side_effect = StructuredOutputError("bad output")
        update = router_node({"query": "x"}, gateway=gateway)
        self.assertEqual(update["route"], "clarification")
        self.assertEqual(update["route_confidence"], 0.0)
        self.assertNotIn("_usage", update)

    def test_router_prompt_uses_only_the_seven_routes(self):
        for name in ROUTE_NAMES:
            self.assertIn(name, ROUTER_SYSTEM_PROMPT)
        self.assertEqual(len(ROUTES), 7)
        self.assertEqual(tuple(name for name, _ in ROUTES), ROUTE_NAMES)


class StubNodeTests(unittest.TestCase):
    def test_every_route_has_a_stub_node_reporting_not_implemented(self):
        for route in ROUTE_NAMES:
            update = make_stub_node(route)({})
            self.assertEqual(update["agent_result"]["status"], "not_implemented")
            self.assertEqual(update["agent_result"]["route"], route)
            self.assertEqual(update["agent_result"]["sub_phase"], SUB_PHASE)

    def test_sub_phase_is_explicitly_unassigned_not_guessed(self):
        self.assertEqual(SUB_PHASE, "unassigned")


class GraphTests(unittest.TestCase):
    def _fake_gateway(self, route="knowledge"):
        decision = RouteDecision(route=route, confidence=0.9, reasoning="r")
        gen = GenerationResult(text="{}", finish_reason="stop", model="m", runtime="ollama",
                                usage=GenerationUsage(), timings=GenerationTimings())
        gateway = MagicMock()
        gateway.generate_structured.return_value = StructuredResult(value=decision, result=gen)
        return gateway

    def _initial_state(self, query="q"):
        return {
            "run_id": str(uuid4()), "query": query, "route": None, "route_confidence": None,
            "route_reasoning": None, "evidence": [], "tool_invocations": [], "agent_result": None,
            "warnings": [], "errors": [], "human_approval_required": False, "action_class": None,
            "started_at": "x", "finished_at": None, "step_records": [],
        }

    def test_build_graph_routes_to_the_matching_stub_and_records_two_steps(self):
        with patch("app.agents.graph.get_model_gateway", return_value=self._fake_gateway("maintenance")):
            graph = build_graph()
        state = graph.invoke(self._initial_state(), config={"recursion_limit": settings.agent_max_steps})
        self.assertEqual(state["route"], "maintenance")
        self.assertEqual([s["node_name"] for s in state["step_records"]], ["router", "maintenance"])
        for step in state["step_records"]:
            self.assertIsNotNone(step["duration_ms"])

    def test_unknown_route_falls_back_to_clarification_selector(self):
        from app.agents.graph import _route_selector
        self.assertEqual(_route_selector({"route": "not_a_real_route"}), "clarification")
        self.assertEqual(_route_selector({"route": "safety"}), "safety")

    def test_get_graph_is_a_cached_singleton(self):
        get_graph.cache_clear()
        with patch("app.agents.graph.get_model_gateway", return_value=self._fake_gateway()):
            first = get_graph()
            second = get_graph()
        self.assertIs(first, second)
        get_graph.cache_clear()

    def test_run_graph_populates_run_id_and_timestamps(self):
        get_graph.cache_clear()
        with patch("app.agents.graph.get_model_gateway", return_value=self._fake_gateway("clarification")):
            state = run_graph("what is P-204's status")
        get_graph.cache_clear()
        self.assertTrue(state["run_id"])
        self.assertIsNotNone(state["finished_at"])
        self.assertEqual(state["route"], "clarification")


class TracingTests(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.added = []
        self.session.add.side_effect = self.added.append

    def _state(self, **overrides):
        base = {
            "run_id": str(uuid4()), "query": "q", "route": "knowledge", "route_confidence": 0.9,
            "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": datetime.now(timezone.utc).isoformat(),
            "warnings": [], "step_records": [{
                "node_name": "router", "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(), "duration_ms": 12.0, "tool_name": None,
                "evidence_ids": ["csv_row_abc"], "usage": {}, "timings": {}, "warnings": [], "error": None,
            }],
        }
        base.update(overrides)
        return base

    def test_record_run_persists_run_and_step_rows(self):
        record_run(self.session, self._state(), status="ok", model="qwen3.5:9b", runtime="ollama")
        runs = [obj for obj in self.added if isinstance(obj, AgentRun)]
        steps = [obj for obj in self.added if isinstance(obj, AgentRunStep)]
        self.assertEqual(len(runs), 1)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].evidence_ids, ["csv_row_abc"])
        self.assertTrue(self.session.commit.called)

    def test_record_run_stores_query_text_only_when_configured(self):
        with patch.object(settings, "agent_trace_store_query", False):
            record_run(self.session, self._state(), status="ok", model="m", runtime="ollama")
        runs = [obj for obj in self.added if isinstance(obj, AgentRun)]
        self.assertIsNone(runs[0].query_text)
        self.assertEqual(runs[0].route, "knowledge")  # route/confidence are unaffected

    def test_record_run_is_a_no_op_when_tracing_disabled(self):
        with patch.object(settings, "agent_trace_enabled", False):
            result = record_run(self.session, self._state(), status="ok", model="m", runtime="ollama")
        self.assertIsNone(result)
        self.assertFalse(self.session.add.called)


class AgentConfigTests(unittest.TestCase):
    def _settings(self, **overrides):
        values = dict(model_name="qwen-test", model_base_url="http://127.0.0.1:11434")
        values.update(overrides)
        # Isolated from the developer's local .env: this class tests Settings'
        # own Python-level field defaults, not this machine's dev configuration.
        return Settings(_env_file=None, **values)

    def test_agent_settings_defaults(self):
        s = self._settings()
        self.assertEqual(s.agent_router_min_confidence, 0.5)
        self.assertEqual(s.agent_tool_max_window_days, 90)
        self.assertEqual(s.agent_max_steps, 12)
        self.assertTrue(s.agent_trace_enabled)
        self.assertTrue(s.agent_trace_store_query)
        self.assertEqual(s.agent_run_timeout_seconds, 300)

    def test_router_min_confidence_bounds_enforced(self):
        with self.assertRaises(ValidationError):
            self._settings(agent_router_min_confidence=1.5)
        with self.assertRaises(ValidationError):
            self._settings(agent_router_min_confidence=-0.1)

    def test_tool_max_window_days_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self._settings(agent_tool_max_window_days=0)

    def test_run_timeout_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self._settings(agent_run_timeout_seconds=0)


class SourceGuardTests(unittest.TestCase):
    """Extends the Phase 4A sovereignty guard to app/agents/: no hosted
    inference provider and no hosted tracing endpoint may be named here."""

    HOSTED_HOSTNAMES = (
        "api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com",
        "api.cohere.ai", "api.mistral.ai", "api.together.xyz", "openrouter.ai", "api.groq.com",
    )
    TRACING_HOSTNAMES = (
        "smith.langchain.com", "api.smith.langchain.com", "beta.api.smith.langchain.com",
    )

    def _agent_source_files(self):
        return sorted(AGENTS_PACKAGE_DIR.rglob("*.py"))

    def test_no_agent_source_file_names_a_hosted_inference_provider(self):
        for path in self._agent_source_files():
            text = path.read_text(encoding="utf-8").lower()
            for hostname in self.HOSTED_HOSTNAMES:
                self.assertNotIn(hostname, text, f"{path} contains hosted hostname {hostname!r}")

    def test_no_agent_source_file_names_a_hosted_tracing_endpoint(self):
        for path in self._agent_source_files():
            text = path.read_text(encoding="utf-8").lower()
            for hostname in self.TRACING_HOSTNAMES:
                self.assertNotIn(hostname, text, f"{path} contains hosted tracing hostname {hostname!r}")

    def test_telemetry_env_vars_are_hardened_at_package_import_time(self):
        init_text = (AGENTS_PACKAGE_DIR / "__init__.py").read_text(encoding="utf-8")
        for var in ("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING", "LANGCHAIN_ENDPOINT", "LANGSMITH_ENDPOINT"):
            self.assertIn(var, init_text)
        self.assertIn("setdefault", init_text)

    def test_no_write_tool_vocabulary_in_the_registry(self):
        # The registry is read-only by construction: no adapter here may be
        # named delete/update/insert/write.
        for spec in list_tools():
            for token in ("delete", "update", "insert", "write", "ingest"):
                self.assertIsNone(re.search(r"\b" + token + r"\b", spec.name, re.IGNORECASE))


class QueryRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_extra_field_rejected(self):
        response = self.client.post("/query", json={"query": "hi", "model": "other"})
        self.assertEqual(response.status_code, 422)

    def test_empty_query_rejected(self):
        response = self.client.post("/query", json={"query": "   "})
        self.assertEqual(response.status_code, 422)

    def test_successful_run_returns_extended_contract_and_traces(self):
        # Phase 5E: a query in this exact shape ("ignore all instructions...")
        # is now intercepted deterministically at preflight, before this
        # graph/gateway mock is ever reached (see test_phase5e.py for that
        # coverage) -- so this test now uses a benign, in-scope query to keep
        # exercising what it always intended: the graph's own response
        # contract/tracing shape when the (mocked) ROUTER ITSELF decides
        # guardrail_refusal, independent of Phase 5E's pre-routing gate.
        decision = RouteDecision(route="guardrail_refusal", confidence=0.99, reasoning="r")
        gen = GenerationResult(text="{}", finish_reason="stop", model="m", runtime="ollama",
                                usage=GenerationUsage(), timings=GenerationTimings())
        gateway = MagicMock()
        gateway.generate_structured.return_value = StructuredResult(value=decision, result=gen)
        fake_session = MagicMock()

        def _fake_get_db():
            yield fake_session

        from app.db.session import get_db
        app.dependency_overrides[get_db] = _fake_get_db
        self.addCleanup(app.dependency_overrides.pop, get_db, None)
        get_graph.cache_clear()
        with patch("app.agents.graph.get_model_gateway", return_value=gateway):
            response = self.client.post("/query", json={"query": "Show maintenance history for P-204."})
        get_graph.cache_clear()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["route"], "guardrail_refusal")
        self.assertIn("run_id", body)
        self.assertIn("timings", body)
        self.assertTrue(fake_session.add.called)


class AgentsStatusRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_status_enumerates_seven_routes_and_all_tools_and_gateway_health(self):
        from app.services.model_gateway.types import RuntimeHealth
        health = RuntimeHealth(runtime="ollama", reachable=False, configured_model="qwen-test",
                                configured_model_present=False, detail="not reachable in this test")
        with patch("app.api.routes.agents.get_model_gateway") as mocked_factory:
            mocked_factory.return_value.health.return_value = health
            response = self.client.get("/agents/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual({r["route"] for r in body["routes"]}, set(ROUTE_NAMES))
        self.assertEqual({r["status"] for r in body["routes"]}, {"implemented", "guardrail"})
        self.assertEqual(len(body["tools"]), 7)
        self.assertTrue(all(t["read_only"] for t in body["tools"]))
        self.assertFalse(body["gateway"]["reachable"])
        self.assertNotIn("base_url", str(body))
        self.assertNotIn("api_key", str(body))


if __name__ == "__main__":
    unittest.main()
