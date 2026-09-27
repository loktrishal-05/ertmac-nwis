"""Risk policy, real gateway contracts and HTTP authority; no model inference."""
import json
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import Settings, settings
from app.services import model_routing as routing, execution_observability as obs
from app.services.model_gateway import (
    ChatMessage, GenerationResult, GenerationUsage, GenerationTimings, ModelGateway,
    ModelInfo, ModelConfigurationError, ModelUnavailableError, StructuredOutputError,
)
from app.services.model_gateway.gateway import get_model_gateway


class Label(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    label: str


def output(text='{"label":"ready"}', **overrides):
    return GenerationResult(text=text, finish_reason="stop", model=settings.fast_model, runtime="ollama",
        usage=GenerationUsage(prompt_tokens=10, completion_tokens=4), timings=GenerationTimings(), **overrides)


class ModelRoutingTests(unittest.TestCase):
    def select(self, query="Format a title", task="formatting", **signals):
        return routing.select_model(query, task=task, signals=routing.RiskSignals(**signals))

    def factory(self, outcomes):
        self.runtime = Mock()
        self.runtime.list_models.return_value = [ModelInfo(name=settings.fast_model), ModelInfo(name=settings.primary_model)]
        self.runtime.chat.side_effect = outcomes
        return Mock(side_effect=lambda role: ModelGateway(routing.model_config(settings, role), runtime=self.runtime))

    def generate(self, factory, **kwargs):
        return routing.generate_bounded(query="Format a title", task="formatting",
            messages=[ChatMessage(role="user", content="Format a title")], schema=Label,
            gateway_factory=factory, **kwargs)

    def test_bounded_tasks_are_fast_eligible(self):
        for task in ("formatting", "schema_transform", "metadata", "classification", "helper_text", "strategy"):
            with self.subTest(task=task):
                decision = self.select("Convert these supplied display labels to JSON", task)
                self.assertEqual(decision["routing_class"], "FAST_LOW_RISK")
                self.assertEqual(decision["model_selected"], "qwen3.5:4b")

    def test_sensitive_language_always_primary(self):
        for text, expected in (("Assess pump safety", "SAFETY_CRITICAL"),
                ("Summarize two documents", "COMPLEX_SYNTHESIS"),
                ("Review startup isolation", "SAFETY_CRITICAL"),
                ("Assess environmental compliance", "SAFETY_CRITICAL"),
                ("Diagnose maintenance conflict", "DEEP_EVIDENCE"),
                ("Verify P&ID topology", "DEEP_EVIDENCE")):
            with self.subTest(text=text):
                decision = self.select(text)
                self.assertEqual(decision["model_selected"], settings.primary_model)
                self.assertEqual(decision["routing_class"], expected)

    def test_all_deterministic_escalation_signals(self):
        for signals in ({"evidence_required": True}, {"evidence_insufficient": True},
                {"multiple_documents_required": True}, {"document_count": 2},
                {"conflicting_evidence": True}, {"safety_context": True}, {"approval_bearing": True},
                {"ocr_confidence": 0.59}, {"pid_uncertainty": True}, {"high_risk_tools": True},
                {"missing_verified_knowledge": True}, {"multi_agent": True}, {"complex_synthesis": True},
                {"critical_tag_verification": True}, {"previous_fast_failure": True}, {"force_primary": True}):
            with self.subTest(signals=signals):
                decision = self.select(**signals)
                self.assertEqual(decision["model_role"], "primary")
                self.assertTrue(decision["escalated"])
                self.assertTrue(decision["escalation_reason"])

    def test_unknown_unbounded_or_non_english_never_grants_fast(self):
        for task, query in ((None, "simple request"), ("unknown", "simple request"),
                            ("formatting", "x" * 2049), ("classification", "सुरक्षा")):
            self.assertEqual(self.select(query, task)["model_role"], "primary")

    def test_rag_mgs_and_unclassified_queries_require_primary(self):
        for path in ("HYBRID_RAG_PATH", "MGS_PATH", "EXISTING_AGENTIC_PATH"):
            for task in (None, "formatting"):
                self.assertEqual(routing.select_model("Explain documentation", task=task, requested_path=path)["model_role"], "primary")

    def test_structured_transformation_uses_existing_fast_adapter(self):
        factory = self.factory([output()])
        result, decision = self.generate(factory)
        self.assertEqual(result.value.label, "ready")
        self.assertEqual(decision["model_role"], "fast")
        self.assertEqual(decision["selected_model"], settings.fast_model)
        self.assertEqual(self.runtime.chat.call_args.kwargs["model"], settings.fast_model)
        self.assertEqual(self.runtime.chat.call_args.kwargs["max_output_tokens"], 256)
        self.assertIsNone(self.runtime.chat.call_args.kwargs["tools"])

    def test_fast_structural_failure_escalates_once_with_metrics(self):
        factory = self.factory([output("not JSON"), output()])
        @obs.observe_query
        def run():
            result, decision = self.generate(factory)
            metrics = obs.routing_snapshot()
            self.assertEqual(result.value.label, "ready")
            self.assertEqual(decision["escalation_reason"], "fast_contract_failure")
            self.assertEqual(metrics["selected_model"], settings.primary_model)
            self.assertEqual([c["selected_model"] for c in metrics["model_stages"]], [settings.fast_model, settings.primary_model])
            self.assertEqual(metrics["model_call_count"], 2)
            self.assertEqual(metrics["input_tokens"], 20)
            self.assertEqual(metrics["output_tokens"], 8)
            self.assertGreaterEqual(metrics["generation_latency_ms"], 0)
            self.assertNotIn("not JSON", str(metrics))
            self.assertNotIn("chain_of_thought", str(metrics))
        run()
        self.assertEqual([call.kwargs["model"] for call in self.runtime.chat.call_args_list], [settings.fast_model, settings.primary_model])
        self.assertIsNone(obs._current.get())

    def test_contract_duplicate_keys_truncation_and_semantics_escalate(self):
        for first in (output('{"label":"a","label":"b"}'), output(truncated=True), output('{"label":"unsafe"}')):
            with self.subTest(first=first.text):
                factory = self.factory([first, output()])
                def contract(value):
                    if value.label != "ready": raise ValueError("Invalid display label")
                self.assertEqual(self.generate(factory, contract=contract)[1]["model_role"], "primary")
                self.assertEqual(self.runtime.chat.call_count, 2)

    def test_fast_runtime_failure_escalates_and_primary_failure_never_downgrades(self):
        factory = self.factory([ModelUnavailableError("offline"), output()])
        self.assertEqual(self.generate(factory)[1]["escalation_reason"], "fast_runtime_failure")
        factory = self.factory([ModelUnavailableError("offline")])
        with self.assertRaises(ModelUnavailableError):
            self.generate(factory, signals=routing.RiskSignals(safety_context=True))
        self.assertEqual([c.args[0] for c in factory.call_args_list], ["primary"])

    def test_primary_contract_failure_is_not_returned_as_an_answer(self):
        factory = self.factory([output("bad"), output("still bad")])
        with self.assertRaises(StructuredOutputError): self.generate(factory)
        self.assertEqual(self.runtime.chat.call_count, 2)

    def test_actual_message_risk_and_bounds_override_benign_description(self):
        for text in ("Plan a safe shutdown", "x" * 2049):
            factory = self.factory([output()])
            _, decision = routing.generate_bounded(query="Format a title", task="formatting",
                messages=[ChatMessage(role="user", content=text)], schema=Label, gateway_factory=factory)
            self.assertEqual(decision["model_role"], "primary")

    def test_config_defaults_env_and_hosted_profiles(self):
        with patch.dict("os.environ", {"FAST_MODEL": "qwen3.5:4b", "PRIMARY_MODEL": "qwen3.5:9b"}):
            config = Settings(model_name="qwen-test", _env_file=None)
        self.assertEqual(config.fast_model, settings.fast_model)
        self.assertEqual(config.primary_model, settings.primary_model)
        for values in ({"FAST_MODEL": "gpt-4o"}, {"PRIMARY_MODEL": "qwen3.5:4b"}, {"FAST_MODEL": "qwen3.5:4b-cloud"}):
            with patch.dict("os.environ", values), self.assertRaises(ValidationError):
                Settings(model_name="qwen-test", _env_file=None)
        for update in ({"primary_model": "qwen3.5:4b"}, {"fast_model": "hosted"},
                {"model_base_url": "https://api.openai.com", "model_allowed_hosts": "api.openai.com"}):
            with self.assertRaises(ModelConfigurationError):
                routing.select_model("Format a title", task="formatting", config=settings.model_copy(update=update))

    def test_default_gateway_cannot_inherit_fast_legacy_model(self):
        get_model_gateway.cache_clear()
        self.addCleanup(get_model_gateway.cache_clear)
        with patch.object(settings, "model_name", settings.fast_model):
            self.assertEqual(get_model_gateway()._settings.model_name, settings.primary_model)
            self.assertEqual(get_model_gateway("fast")._settings.model_name, settings.fast_model)

    def test_new_signals_are_strict_server_facts(self):
        for data in ({"approval_bearing": "false"}, {"confidence": 0.99}, {"ocr_confidence": -1}):
            with self.assertRaises(ValidationError): routing.RiskSignals(**data)


class RoutingAuthorityTests(unittest.TestCase):
    def setUp(self):
        import test_phase11_security
        test_phase11_security.Phase11SecurityTests.setUp(self)
        from app.main import app
        from app.api.deps import get_optional_current_user
        self.app = app
        app.dependency_overrides[get_optional_current_user] = lambda: self.requester
        self.addCleanup(app.dependency_overrides.pop, get_optional_current_user)

    def test_http_cannot_choose_model_or_role(self):
        with TestClient(self.app) as client:
            for field in ("model", "model_role", "routing_class", "task", "signals", "fast_model"):
                self.assertEqual(client.post("/query", json={"query": "Show pump history", field: "fast"}).status_code, 422)
            self.assertEqual(client.post("/documents/ingest", json={}).status_code, 403)
        from app.api.deps import get_optional_current_user
        self.app.dependency_overrides[get_optional_current_user] = lambda: None
        with TestClient(self.app) as client:
            self.assertEqual(client.post("/query", json={"query": "Show pump history"}).status_code, 401)

    def test_primary_runtime_failure_on_safety_http_is_safe(self):
        runtime = Mock()
        runtime.chat.side_effect = ModelUnavailableError("offline")
        get_model_gateway.cache_clear()
        self.addCleanup(get_model_gateway.cache_clear)
        with patch("app.services.model_gateway.gateway.get_runtime", return_value=runtime), TestClient(self.app) as client:
            response = client.post("/query", json={"query": "Assess pump safety"})
        self.assertEqual(response.status_code, 503, response.text)
        self.assertTrue(runtime.chat.called)
        self.assertEqual({c.kwargs["model"] for c in runtime.chat.call_args_list}, {settings.primary_model})

    def test_routing_metadata_is_additive_and_does_not_approve(self):
        from test_phase5a import state
        request = {"query": "Review pump recommendation"}
        with patch("app.api.routes.query.run_graph", return_value=state(approved=True)), TestClient(self.app) as client:
            response = client.post("/query", json=request)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["governance_status"], "PENDING_REVIEW")
        self.assertTrue(body["human_review_required"])
        self.assertEqual(body["execution"]["model_selected"], settings.primary_model)
        self.assertEqual(body["execution"]["routing_class"], "DEEP_EVIDENCE")
        self.assertNotIn('"approved"', json.dumps(body["agent_result"]))

    def test_system1_escalation_survives_primary_graph_and_governed_replay(self):
        from uuid import uuid4
        from test_phase5a import state
        from app.services import adaptive_execution
        runtime = Mock()
        runtime.list_models.return_value = [ModelInfo(name=settings.fast_model), ModelInfo(name=settings.primary_model)]
        runtime.chat.side_effect = [output("invalid"), output(json.dumps({
            "path": "HYBRID_RAG_PATH", "reason_code": "document_lookup",
            "requires_deep_reasoning": False, "requires_multiple_documents": False}))]
        factory = lambda role: ModelGateway(routing.model_config(settings, role), runtime=runtime)
        request = {"query": "Explain P-204 documentation", "request_id": str(uuid4())}
        with patch.object(settings, "system1_enabled", True), \
                patch.object(adaptive_execution, "get_model_gateway", side_effect=factory), \
                patch("app.api.routes.query.run_graph", return_value=state()) as graph, TestClient(self.app) as client:
            response = client.post("/query", json=request)
            replay = client.post("/query", json=request)
        self.assertEqual(response.status_code, 200, response.text)
        execution = response.json()["execution"]
        self.assertEqual(execution, replay.json()["execution"])
        self.assertEqual(execution["model_call_count"], 2)
        self.assertEqual(execution["model_selected"], settings.primary_model)
        self.assertEqual(execution["escalation_reason"], "fast_contract_failure")
        self.assertEqual(execution["routing_history"][0]["model_role"], "fast")
        self.assertEqual(response.json()["governance_status"], "PENDING_REVIEW")
        graph.assert_called_once()


if __name__ == "__main__":
    unittest.main()
