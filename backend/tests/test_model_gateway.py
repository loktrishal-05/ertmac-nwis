"""Phase 4A model-gateway tests. Fake transport only (httpx.MockTransport); no
live model, no benchmark content, no new test dependency."""
import json
import re
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import Settings
from app.main import app
from app.services.model_gateway import (
    ChatMessage,
    ModelConfigurationError,
    ModelGatewayError,
    ModelRuntimeError,
    ModelTimeoutError,
    ModelUnavailableError,
    StructuredOutputError,
    ToolCallProtocolError,
    ToolSpec,
)
from app.services.model_gateway.gateway import ModelGateway
from app.services.model_gateway.ollama_runtime import OllamaRuntime
from app.services.model_gateway.registry import get_runtime, validate_model_url
from app.services.model_gateway.schemas import json_schema_for
from app.services.model_gateway.vllm_runtime import VLLMRuntime

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "app" / "services" / "model_gateway"

HOSTED_HOSTNAMES = (
    "api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com",
    "api.cohere.ai", "api.mistral.ai", "api.together.xyz", "openrouter.ai", "api.groq.com",
)
RUNTIME_SPECIFIC_TOKENS = ("keep_alive", "num_predict", "num_ctx", "format", "api/chat", "ollama")


def make_settings(**overrides):
    values = dict(
        model_runtime="ollama", model_name="qwen-test", model_base_url="http://127.0.0.1:11434",
        model_allowed_hosts="127.0.0.1,localhost,::1", model_connect_timeout_seconds=1,
        model_timeout_seconds=5, model_first_load_timeout_seconds=5, model_max_retries=2,
        model_temperature=0.0, model_seed=42, model_context_window=8192, model_max_output_tokens=256,
        model_keep_alive="30m", model_structured_repair_attempts=1, model_log_prompts=False,
    )
    values.update(overrides)
    return Settings(**values)


def chat_response(**overrides):
    body = {
        "message": {"role": "assistant", "content": "hello"},
        "done_reason": "stop", "done": True,
        "total_duration": 2_000_000_000, "load_duration": 500_000_000,
        "prompt_eval_count": 10, "prompt_eval_duration": 300_000_000,
        "eval_count": 5, "eval_duration": 700_000_000,
    }
    body.update(overrides)
    return httpx.Response(200, json=body)


def runtime_with(handler, **settings_overrides):
    settings = make_settings(**settings_overrides)
    return OllamaRuntime(settings, transport=httpx.MockTransport(handler))


def default_chat_kwargs(**overrides):
    kwargs = dict(
        messages=[ChatMessage(role="user", content="hi")], model="qwen-test", temperature=0.0, seed=42,
        max_output_tokens=100, context_window=8192, stop=None, json_schema=None, tools=None, think=None,
        timeout_seconds=5,
    )
    kwargs.update(overrides)
    return kwargs


class SmallSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_tag: str
    value: float


class NestedSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inner: SmallSchema
    label: str


class ConfigurationTests(unittest.TestCase):
    def test_allowed_host_accepted(self):
        settings = make_settings(model_base_url="http://127.0.0.1:11434", model_allowed_hosts="127.0.0.1")
        self.assertEqual(settings.model_base_url, "http://127.0.0.1:11434")

    def test_public_host_rejected(self):
        with self.assertRaises(ValidationError):
            make_settings(model_base_url="http://example.com:11434", model_allowed_hosts="127.0.0.1")

    def test_each_denylisted_provider_rejected_even_if_allowlisted(self):
        for host in (
            "api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com",
            "api.cohere.ai", "api.mistral.ai", "api.together.xyz", "openrouter.ai",
            "api.groq.com", "myorg.azure.com", "bedrock-runtime.us-east-1.amazonaws.com",
        ):
            with self.assertRaises(ModelConfigurationError, msg=host):
                # Denylist is independent of the allowlist: even a host explicitly
                # allowlisted by mistake must still be rejected.
                validate_model_url(f"https://{host}", {host})

    def test_unknown_runtime_rejected(self):
        with self.assertRaises(ValidationError):
            make_settings(model_runtime="claude")

    def test_empty_model_name_fails_with_remedy_in_message(self):
        with self.assertRaises(ValidationError) as ctx:
            make_settings(model_name="")
        self.assertIn("ollama list", str(ctx.exception))

    def test_extra_forbid_rejects_routing_fields(self):
        for field in ("model", "base_url", "runtime", "api_key", "endpoint"):
            with self.assertRaises(ValidationError, msg=field):
                ChatMessage(role="user", content="hi", **{field: "x"})
            with self.assertRaises(ValidationError, msg=field):
                ToolSpec(name="t", description="d", parameters={}, **{field: "x"})

    def test_get_runtime_selects_ollama_and_vllm(self):
        settings = make_settings()
        self.assertIsInstance(get_runtime("ollama", settings), OllamaRuntime)
        self.assertIsInstance(get_runtime("vllm", settings), VLLMRuntime)
        with self.assertRaises(ModelConfigurationError):
            get_runtime("bogus", settings)


class SourceGuardTests(unittest.TestCase):
    """These two tests are what keeps the sovereignty and swappability claims true over time."""

    def test_no_file_other_than_the_denylist_names_a_hosted_provider(self):
        for path in sorted(PACKAGE_DIR.glob("*.py")):
            if path.name == "registry.py":
                continue
            text = path.read_text(encoding="utf-8").lower()
            for hostname in HOSTED_HOSTNAMES:
                self.assertNotIn(hostname, text, f"{path.name} contains hosted hostname {hostname!r}")

    def test_registry_denylist_still_lists_every_hosted_provider(self):
        text = (PACKAGE_DIR / "registry.py").read_text(encoding="utf-8")
        for hostname in HOSTED_HOSTNAMES:
            self.assertIn(hostname, text)

    def test_gateway_and_base_contain_no_runtime_specific_vocabulary(self):
        for filename in ("gateway.py", "base.py"):
            text = (PACKAGE_DIR / filename).read_text(encoding="utf-8")
            for token in RUNTIME_SPECIFIC_TOKENS:
                pattern = r"\b" + re.escape(token) + r"\b"
                self.assertIsNone(re.search(pattern, text, re.IGNORECASE), f"{filename} contains {token!r}")


class RequestConstructionTests(unittest.TestCase):
    def test_options_stream_and_no_format_without_schema(self):
        captured = {}

        def handler(request):
            captured["body"] = json.loads(request.content)
            return chat_response()

        runtime = runtime_with(handler)
        runtime.chat(**default_chat_kwargs())
        body = captured["body"]
        self.assertEqual(body["stream"], False)
        self.assertEqual(body["options"]["temperature"], 0.0)
        self.assertEqual(body["options"]["seed"], 42)
        self.assertEqual(body["options"]["num_ctx"], 8192)
        self.assertEqual(body["options"]["num_predict"], 100)
        self.assertNotIn("format", body)

    def test_format_present_only_when_schema_supplied(self):
        captured = {}

        def handler(request):
            captured["body"] = json.loads(request.content)
            return chat_response()

        runtime = runtime_with(handler)
        runtime.chat(**default_chat_kwargs(json_schema={"type": "object"}))
        self.assertEqual(captured["body"]["format"], {"type": "object"})

    def test_think_sent_when_set_and_omitted_when_none(self):
        captured = {}

        def handler(request):
            captured["body"] = json.loads(request.content)
            return chat_response()

        runtime = runtime_with(handler)
        runtime.chat(**default_chat_kwargs(think=None))
        self.assertNotIn("think", captured["body"])

        runtime.chat(**default_chat_kwargs(think=False))
        self.assertEqual(captured["body"]["think"], False)

        runtime.chat(**default_chat_kwargs(think=True))
        self.assertEqual(captured["body"]["think"], True)


class StructuredOutputTests(unittest.TestCase):
    def test_valid_first_pass(self):
        def handler(request):
            return chat_response(message={"role": "assistant", "content": '{"equipment_tag": "FIX-001", "value": 1.5}'})

        settings = make_settings()
        gateway = ModelGateway(settings, runtime=OllamaRuntime(settings, transport=httpx.MockTransport(handler)))
        result = gateway.generate_structured(messages=[ChatMessage(role="user", content="go")], schema=SmallSchema)
        self.assertEqual(result.value.equipment_tag, "FIX-001")
        self.assertEqual(result.result.repair_attempts, 0)

    def test_invalid_then_repaired(self):
        calls = []

        def handler(request):
            calls.append(json.loads(request.content))
            if len(calls) == 1:
                return chat_response(message={"role": "assistant", "content": '{"equipment_tag": "FIX-001"}'})
            return chat_response(message={"role": "assistant", "content": '{"equipment_tag": "FIX-001", "value": 2.0}'})

        settings = make_settings()
        gateway = ModelGateway(settings, runtime=OllamaRuntime(settings, transport=httpx.MockTransport(handler)))
        result = gateway.generate_structured(messages=[ChatMessage(role="user", content="go")], schema=SmallSchema)
        self.assertEqual(result.result.repair_attempts, 1)
        self.assertEqual(len(calls), 2)
        repair_message = calls[1]["messages"][-1]["content"]
        self.assertIn("did not satisfy the required schema", repair_message)
        self.assertNotIn("2.0", repair_message)  # never leaks the expected value

    def test_invalid_twice_raises_with_raw_text_and_errors_preserved(self):
        def handler(request):
            return chat_response(message={"role": "assistant", "content": '{"equipment_tag": "FIX-001"}'})

        settings = make_settings(model_structured_repair_attempts=1)
        gateway = ModelGateway(settings, runtime=OllamaRuntime(settings, transport=httpx.MockTransport(handler)))
        with self.assertRaises(StructuredOutputError) as ctx:
            gateway.generate_structured(messages=[ChatMessage(role="user", content="go")], schema=SmallSchema)
        self.assertIn("equipment_tag", ctx.exception.raw_text)
        self.assertIsNotNone(ctx.exception.validation_errors)

    def test_fenced_json_is_stripped(self):
        def handler(request):
            return chat_response(message={"role": "assistant", "content": '```json\n{"equipment_tag": "FIX-001", "value": 1.0}\n```'})

        settings = make_settings()
        gateway = ModelGateway(settings, runtime=OllamaRuntime(settings, transport=httpx.MockTransport(handler)))
        result = gateway.generate_structured(messages=[ChatMessage(role="user", content="go")], schema=SmallSchema)
        self.assertEqual(result.value.value, 1.0)

    def test_trailing_prose_is_a_failure_not_salvage(self):
        def handler(request):
            return chat_response(message={
                "role": "assistant",
                "content": 'Sure! {"equipment_tag": "FIX-001", "value": 1.0} Let me know if that helps.',
            })

        settings = make_settings(model_structured_repair_attempts=0)
        gateway = ModelGateway(settings, runtime=OllamaRuntime(settings, transport=httpx.MockTransport(handler)))
        with self.assertRaises(StructuredOutputError):
            gateway.generate_structured(messages=[ChatMessage(role="user", content="go")], schema=SmallSchema)

    def test_nested_defs_refs_are_inlined(self):
        schema = json_schema_for(NestedSchema)
        self.assertNotIn("$defs", schema)
        self.assertNotIn("$ref", json.dumps(schema))
        self.assertEqual(schema["properties"]["inner"]["properties"]["equipment_tag"]["type"], "string")

    def test_nested_schema_generation_end_to_end(self):
        def handler(request):
            return chat_response(message={
                "role": "assistant",
                "content": '{"inner": {"equipment_tag": "FIX-001", "value": 3.0}, "label": "synthetic"}',
            })

        settings = make_settings()
        gateway = ModelGateway(settings, runtime=OllamaRuntime(settings, transport=httpx.MockTransport(handler)))
        result = gateway.generate_structured(messages=[ChatMessage(role="user", content="go")], schema=NestedSchema)
        self.assertEqual(result.value.inner.equipment_tag, "FIX-001")
        self.assertEqual(result.value.label, "synthetic")


class ToolCallTests(unittest.TestCase):
    def test_well_formed_call_parsed(self):
        def handler(request):
            return chat_response(message={
                "role": "assistant", "content": "",
                "tool_calls": [{"function": {"name": "lookup", "arguments": {"tag": "FIX-001"}}}],
            }, done_reason=None)

        settings = make_settings()
        gateway = ModelGateway(settings, runtime=OllamaRuntime(settings, transport=httpx.MockTransport(handler)))
        tools = [ToolSpec(name="lookup", description="read-only lookup", parameters={"type": "object"})]
        result = gateway.generate_with_tools(messages=[ChatMessage(role="user", content="go")], tools=tools)
        self.assertEqual(result.tool_calls[0].name, "lookup")
        self.assertEqual(result.tool_calls[0].arguments, {"tag": "FIX-001"})
        self.assertEqual(result.finish_reason, "tool_calls")

    def test_name_outside_supplied_specs_is_rejected(self):
        def handler(request):
            return chat_response(message={
                "role": "assistant", "content": "",
                "tool_calls": [{"function": {"name": "disable_alarm", "arguments": {}}}],
            })

        settings = make_settings()
        gateway = ModelGateway(settings, runtime=OllamaRuntime(settings, transport=httpx.MockTransport(handler)))
        tools = [ToolSpec(name="lookup", description="read-only lookup", parameters={"type": "object"})]
        with self.assertRaises(ToolCallProtocolError):
            gateway.generate_with_tools(messages=[ChatMessage(role="user", content="go")], tools=tools)

    def test_unparseable_arguments_raise_protocol_error(self):
        def handler(request):
            return chat_response(message={
                "role": "assistant", "content": "",
                "tool_calls": [{"function": {"name": "lookup", "arguments": "{not json"}}],
            })

        runtime = runtime_with(handler)
        tools = [ToolSpec(name="lookup", description="d", parameters={})]
        with self.assertRaises(ToolCallProtocolError):
            runtime.chat(**default_chat_kwargs(tools=tools))

    def test_generate_with_tools_has_no_executor(self):
        self.assertFalse(hasattr(ModelGateway, "execute_tool"))
        self.assertFalse(hasattr(ModelGateway, "run_tool"))
        self.assertFalse(hasattr(ModelGateway, "call_tool"))


class ResponseMappingTests(unittest.TestCase):
    def test_usage_and_nanosecond_to_millisecond_conversion(self):
        runtime = runtime_with(lambda request: chat_response())
        result = runtime.chat(**default_chat_kwargs())
        self.assertEqual(result.timings.total_ms, 2000.0)
        self.assertEqual(result.timings.load_ms, 500.0)
        self.assertEqual(result.timings.prompt_eval_ms, 300.0)
        self.assertEqual(result.timings.eval_ms, 700.0)
        self.assertEqual(result.usage.prompt_tokens, 10)
        self.assertEqual(result.usage.completion_tokens, 5)
        self.assertEqual(result.usage.total_tokens, 15)

    def test_truncated_flag_and_warning(self):
        runtime = runtime_with(lambda request: chat_response(done_reason="length"))
        result = runtime.chat(**default_chat_kwargs())
        self.assertTrue(result.truncated)
        self.assertTrue(any("truncated" in w.lower() for w in result.warnings))

    def test_empty_content_warns_never_invents(self):
        runtime = runtime_with(lambda request: chat_response(message={"role": "assistant", "content": ""}))
        result = runtime.chat(**default_chat_kwargs())
        self.assertEqual(result.text, "")
        self.assertTrue(any("empty" in w.lower() for w in result.warnings))


class FailuresAndRetryTests(unittest.TestCase):
    def test_connect_error_raises_unavailable(self):
        def handler(request):
            raise httpx.ConnectError("refused", request=request)

        runtime = runtime_with(handler, model_max_retries=0)
        with self.assertRaises(ModelUnavailableError):
            runtime.list_models()

    def test_read_timeout_raises_timeout_error(self):
        def handler(request):
            raise httpx.ReadTimeout("slow", request=request)

        runtime = runtime_with(handler, model_max_retries=0)
        with self.assertRaises(ModelTimeoutError):
            runtime.list_models()

    def test_missing_tag_lists_installed_tags(self):
        def handler(request):
            if request.url.path == "/api/chat":
                return httpx.Response(404, json={"error": "model not found"})
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b"}]})

        runtime = runtime_with(handler, model_max_retries=0)
        with self.assertRaises(ModelUnavailableError) as ctx:
            runtime.chat(**default_chat_kwargs(model="missing-model"))
        self.assertIn("qwen3.5:9b", str(ctx.exception))

    def test_503_retried_exactly_max_retries_then_raises(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(503, json={"error": "loading"})

        runtime = runtime_with(handler, model_max_retries=2)
        with patch("time.sleep", return_value=None):
            with self.assertRaises(ModelRuntimeError):
                runtime.list_models()
        self.assertEqual(calls["n"], 3)  # initial attempt + 2 retries

    def test_400_is_never_retried(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(400, json={"error": "bad request"})

        runtime = runtime_with(handler, model_max_retries=2)
        with self.assertRaises(ModelRuntimeError):
            runtime.list_models()
        self.assertEqual(calls["n"], 1)

    def test_total_deadline_cap_is_honoured(self):
        def handler(request):
            raise httpx.ConnectError("refused", request=request)

        # 10 retries' full exponential backoff would take far longer than 0.3s;
        # the wall-clock deadline must cut the loop short regardless.
        runtime = runtime_with(handler, model_max_retries=10)
        started = time.monotonic()
        with self.assertRaises(ModelGatewayError):
            runtime._request("GET", "/api/tags", timeout_seconds=0.3)
        self.assertLess(time.monotonic() - started, 2.0)


class HealthAndAPITests(unittest.TestCase):
    def _handler(self, *, version_ok=True, tags=None, ps=None):
        def handler(request):
            if request.url.path == "/api/version":
                if not version_ok:
                    raise httpx.ConnectError("refused", request=request)
                return httpx.Response(200, json={"version": "0.34.0"})
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": tags or []})
            if request.url.path == "/api/ps":
                return httpx.Response(200, json={"models": ps or []})
            return httpx.Response(404)
        return handler

    def test_health_reachable_with_configured_model_present(self):
        handler = self._handler(tags=[{"name": "qwen-test", "digest": "abc", "size": 123,
                                        "details": {"parameter_size": "9B", "quantization_level": "Q4_K_M"}}])
        runtime = runtime_with(handler)
        health = runtime.health()
        self.assertTrue(health.reachable)
        self.assertTrue(health.configured_model_present)
        self.assertEqual(health.runtime_version, "0.34.0")

    def test_health_unreachable(self):
        def handler(request):
            raise httpx.ConnectError("refused", request=request)

        runtime = runtime_with(handler, model_max_retries=0)
        health = runtime.health()
        self.assertFalse(health.reachable)

    def test_health_model_absent(self):
        handler = self._handler(tags=[{"name": "some-other-model"}])
        runtime = runtime_with(handler)
        health = runtime.health()
        self.assertTrue(health.reachable)
        self.assertFalse(health.configured_model_present)

    def test_models_status_route_200_shape_and_no_leaked_secrets(self):
        handler = self._handler(tags=[{"name": "qwen-test"}])
        settings = make_settings()
        fake_runtime = OllamaRuntime(settings, transport=httpx.MockTransport(handler))
        gateway = ModelGateway(settings, runtime=fake_runtime)
        with patch("app.api.routes.models.get_model_gateway", return_value=gateway), \
             patch("app.api.routes.models.settings", settings):
            with TestClient(app) as client:
                response = client.get("/models/status")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["configured_model"], "qwen-test")
        self.assertTrue(body["configured_model_present"])
        raw = json.dumps(body)
        self.assertNotIn("11434", raw)
        self.assertNotIn("base_url", raw.lower())

    def test_models_status_503_when_unreachable(self):
        def handler(request):
            raise httpx.ConnectError("refused", request=request)

        settings = make_settings(model_max_retries=0)
        fake_runtime = OllamaRuntime(settings, transport=httpx.MockTransport(handler))
        gateway = ModelGateway(settings, runtime=fake_runtime)
        with patch("app.api.routes.models.get_model_gateway", return_value=gateway):
            with TestClient(app) as client:
                response = client.get("/models/status")
        self.assertEqual(response.status_code, 503)


class RuntimeAbstractionTests(unittest.TestCase):
    def test_vllm_runtime_raises_not_implemented(self):
        settings = make_settings(model_runtime="vllm")
        gateway = ModelGateway(settings)
        with self.assertRaises(NotImplementedError):
            gateway.health()
        with self.assertRaises(NotImplementedError):
            gateway.list_models()


if __name__ == "__main__":
    unittest.main()
