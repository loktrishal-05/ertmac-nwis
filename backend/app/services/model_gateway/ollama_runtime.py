"""The ONLY file in this package that knows Ollama exists.

Endpoints: POST /api/chat (stream:false always), GET /api/version, GET
/api/tags, GET /api/ps. Every request/response mapping lives here so base.py
and gateway.py can stay runtime-agnostic."""
import json
import random
import time
from threading import Lock

import httpx

from app.services.model_gateway.errors import (
    ModelGatewayError,
    ModelRuntimeError,
    ModelTimeoutError,
    ModelUnavailableError,
    ToolCallProtocolError,
)
from app.services.model_gateway.types import (
    ChatMessage,
    GenerationResult,
    GenerationTimings,
    GenerationUsage,
    ModelInfo,
    RuntimeHealth,
    ToolCall,
    ToolSpec,
)

RETRYABLE_STATUS = frozenset({502, 503, 504})
EXCERPT_LIMIT = 2000


def _ns_to_ms(value) -> float | None:
    return value / 1_000_000 if isinstance(value, (int, float)) else None


class OllamaRuntime:
    name = "ollama"

    def __init__(self, settings, transport: httpx.BaseTransport | None = None):
        self._settings = settings
        self._transport = transport
        self._client_lock = Lock()
        self._client: httpx.Client | None = None

    @property
    def _http(self) -> httpx.Client:
        with self._client_lock:
            if self._client is None:
                self._client = httpx.Client(base_url=self._settings.model_base_url, transport=self._transport,
                                            trust_env=False)
            return self._client

    def _request(self, method: str, path: str, *, json_body: dict | None = None, timeout_seconds: float) -> httpx.Response:
        deadline = time.monotonic() + timeout_seconds
        attempt = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ModelTimeoutError(f"{method} {path} exceeded the total wall-clock deadline")
            connect_timeout = min(self._settings.model_connect_timeout_seconds, remaining)
            request_timeout = httpx.Timeout(connect=connect_timeout, read=remaining, write=remaining, pool=remaining)
            try:
                response = self._http.request(method, path, json=json_body, timeout=request_timeout)
            except httpx.ConnectError as error:
                if attempt >= self._settings.model_max_retries:
                    raise ModelUnavailableError(f"Cannot connect to the configured model runtime ({method} {path})") from error
            except httpx.TimeoutException as error:
                if attempt >= self._settings.model_max_retries:
                    raise ModelTimeoutError(f"{method} {path} timed out") from error
            else:
                if response.status_code == 404:
                    raise ModelUnavailableError(f"{method} {path} returned 404")
                if response.status_code in RETRYABLE_STATUS:
                    if attempt >= self._settings.model_max_retries:
                        raise ModelRuntimeError(f"{method} {path} returned {response.status_code} after retries")
                elif response.status_code >= 400:
                    # Deterministic rejections (4xx) are never retried; a human must fix the request.
                    raise ModelRuntimeError(f"{method} {path} returned {response.status_code}")
                else:
                    return response
            attempt += 1
            backoff = (0.5 * (2 ** (attempt - 1))) + random.uniform(0, 0.25)
            sleep_for = min(backoff, max(deadline - time.monotonic(), 0))
            if sleep_for > 0:
                time.sleep(sleep_for)

    @staticmethod
    def _message_dict(message: ChatMessage) -> dict:
        result = {"role": message.role, "content": message.content}
        if message.tool_call_id is not None:
            result["tool_call_id"] = message.tool_call_id
        if message.name is not None:
            result["name"] = message.name
        return result

    @staticmethod
    def _tool_dict(tool: ToolSpec) -> dict:
        return {"type": "function", "function": {
            "name": tool.name, "description": tool.description, "parameters": tool.parameters,
        }}

    def chat(self, *, messages, model, temperature, seed, max_output_tokens, context_window,
             stop, json_schema, tools, think, timeout_seconds) -> GenerationResult:
        options = {"temperature": temperature}
        if seed is not None:
            options["seed"] = seed
        if max_output_tokens is not None:
            options["num_predict"] = max_output_tokens
        if context_window is not None:
            options["num_ctx"] = context_window
        if stop:
            options["stop"] = list(stop)
        payload = {
            "model": model,
            "messages": [self._message_dict(m) for m in messages],
            "stream": False,
            "options": options,
            "keep_alive": self._settings.model_keep_alive,
        }
        if json_schema is not None:
            payload["format"] = json_schema
        if tools:
            payload["tools"] = [self._tool_dict(t) for t in tools]
        if think is not None:
            # Ollama-specific: suppresses/enables a reasoning-capable model's
            # thinking trace. Omitted entirely when None to preserve the
            # runtime's own default (observed: thinking ON for qwen3.5 here).
            payload["think"] = think

        try:
            response = self._request("POST", "/api/chat", json_body=payload, timeout_seconds=timeout_seconds)
        except ModelUnavailableError as error:
            raise self._enrich_model_missing(model, error)

        try:
            body = response.json()
        except json.JSONDecodeError as error:
            raise ModelRuntimeError("Model runtime returned a response that was not valid JSON") from error
        return self._map_chat_response(body, model=model)

    def _enrich_model_missing(self, model: str, original: ModelUnavailableError) -> ModelUnavailableError:
        try:
            available = [m.name for m in self.list_models()]
        except ModelGatewayError:
            # Connectivity itself is down; don't mask that with a confusing secondary failure.
            return original
        return ModelUnavailableError(
            f"Model '{model}' is not available on this runtime. Installed tags: {available or '(none)'}"
        )

    def _map_chat_response(self, body: dict, *, model: str) -> GenerationResult:
        message = body.get("message") or {}
        text = message.get("content") or ""
        warnings = []

        raw_tool_calls = message.get("tool_calls") or []
        tool_calls = []
        for index, raw_call in enumerate(raw_tool_calls):
            function = raw_call.get("function") or {}
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments) if arguments.strip() else {}
                except json.JSONDecodeError as error:
                    raise ToolCallProtocolError("Tool call arguments were not valid JSON") from error
            tool_calls.append(ToolCall(
                id=raw_call.get("id") or f"call_{index}",
                name=function.get("name", ""),
                arguments=arguments or {},
            ))

        if not text and not tool_calls:
            warnings.append("Model returned empty content.")

        done_reason = body.get("done_reason")
        truncated = done_reason == "length"
        if truncated:
            warnings.append("Response was truncated by the runtime (done_reason=length).")

        if tool_calls:
            finish_reason = "tool_calls"
        elif done_reason in ("stop", "length"):
            finish_reason = done_reason
        else:
            finish_reason = "other" if done_reason else "stop"

        prompt_tokens = body.get("prompt_eval_count")
        completion_tokens = body.get("eval_count")
        total_tokens = (prompt_tokens + completion_tokens) if prompt_tokens is not None and completion_tokens is not None else None
        usage = GenerationUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=total_tokens)
        timings = GenerationTimings(
            total_ms=_ns_to_ms(body.get("total_duration")),
            load_ms=_ns_to_ms(body.get("load_duration")),
            prompt_eval_ms=_ns_to_ms(body.get("prompt_eval_duration")),
            eval_ms=_ns_to_ms(body.get("eval_duration")),
            time_to_first_token_ms=None,  # only meaningful for streamed calls; Phase 4A never streams.
        )
        return GenerationResult(
            text=text, finish_reason=finish_reason, truncated=truncated, tool_calls=tool_calls,
            model=model, runtime=self.name, usage=usage, timings=timings, warnings=warnings,
            repair_attempts=0, raw_response_excerpt=(text[:EXCERPT_LIMIT] if text else None),
        )

    def list_models(self, timeout_seconds: float | None = None) -> list[ModelInfo]:
        timeout = timeout_seconds if timeout_seconds is not None else self._settings.model_timeout_seconds
        response = self._request("GET", "/api/tags", timeout_seconds=timeout)
        try:
            body = response.json()
        except json.JSONDecodeError as error:
            raise ModelRuntimeError("GET /api/tags returned a response that was not valid JSON") from error
        return [self._model_info(item) for item in (body.get("models") or [])]

    @staticmethod
    def _model_info(item: dict, *, use_expiry: bool = False) -> ModelInfo:
        details = item.get("details") or {}
        return ModelInfo(
            name=item.get("name") or item.get("model") or "",
            digest=item.get("digest"),
            size_bytes=item.get("size"),
            parameter_size=details.get("parameter_size"),
            quantization=details.get("quantization_level"),
            modified_at=None if use_expiry else item.get("modified_at"),
        )

    def loaded_models(self, timeout_seconds: float | None = None) -> list[ModelInfo]:
        """GET /api/ps. Richer VRAM/expiry fields exist in the raw response but are
        not part of ModelInfo; see docs/phase4a.md limitations."""
        timeout = timeout_seconds if timeout_seconds is not None else self._settings.model_timeout_seconds
        response = self._request("GET", "/api/ps", timeout_seconds=timeout)
        try:
            body = response.json()
        except json.JSONDecodeError as error:
            raise ModelRuntimeError("GET /api/ps returned a response that was not valid JSON") from error
        return [self._model_info(item, use_expiry=True) for item in (body.get("models") or [])]

    def health(self) -> RuntimeHealth:
        timeout = self._settings.model_first_load_timeout_seconds
        try:
            version_response = self._request("GET", "/api/version", timeout_seconds=timeout)
            runtime_version = version_response.json().get("version")
        except ModelGatewayError as error:
            return RuntimeHealth(
                runtime=self.name, reachable=False, runtime_version=None,
                configured_model=self._settings.model_name, configured_model_present=False,
                available_models=[], loaded_models=[], detail=str(error),
            )
        try:
            available = self.list_models(timeout_seconds=timeout)
        except ModelGatewayError as error:
            return RuntimeHealth(
                runtime=self.name, reachable=True, runtime_version=runtime_version,
                configured_model=self._settings.model_name, configured_model_present=False,
                available_models=[], loaded_models=[], detail=str(error),
            )
        names = [m.name for m in available]
        try:
            loaded = self.loaded_models(timeout_seconds=timeout)
        except ModelGatewayError:
            loaded = []
        return RuntimeHealth(
            runtime=self.name, reachable=True, runtime_version=runtime_version,
            configured_model=self._settings.model_name,
            configured_model_present=self._settings.model_name in names,
            available_models=names, loaded_models=loaded, detail=None,
        )
