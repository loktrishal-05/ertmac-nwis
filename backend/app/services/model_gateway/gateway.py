"""The Gateway facade. Agents (Phase 4B+) import only this module.

This file must stay entirely free of any runtime-specific transport
vocabulary — see base.py. A source-guard test enforces this so the gateway
never silently couples to one runtime.

The gateway owns no prompts: it never injects a system message, safety
preamble, or formatting instruction of its own. The only text it ever adds is
the single bounded structured-output repair turn, which relays nothing more
than the validator's own error message.

`think` is an optional reasoning-mode toggle: None (the default) makes no
request and leaves the runtime's own default behavior unchanged; True/False
asks a reasoning-capable model to show or suppress its reasoning trace. Its
wire-level meaning is entirely runtime-defined — see ollama_runtime.py for
the only runtime that currently interprets it."""
import json
from functools import lru_cache
from threading import Lock
from typing import Literal, Sequence

from pydantic import BaseModel, ValidationError

from app.services.model_gateway.errors import StructuredOutputError, ToolCallProtocolError
from app.services.model_gateway.registry import get_runtime
from app.services.model_gateway.schemas import json_schema_for, parse_and_validate
from app.services.model_gateway.types import (
    ChatMessage,
    GenerationResult,
    ModelInfo,
    RuntimeHealth,
    StructuredResult,
    ToolSpec,
)


class ModelGateway:
    def __init__(self, settings, runtime=None):
        self._settings = settings
        self._runtime_lock = Lock()
        self._runtime_instance = runtime
        self._warmed_up = False

    def _runtime(self):
        with self._runtime_lock:
            if self._runtime_instance is None:
                self._runtime_instance = get_runtime(self._settings.model_runtime, self._settings)
            return self._runtime_instance

    def _effective_timeout(self, timeout_seconds: float | None) -> float:
        if timeout_seconds is not None:
            return timeout_seconds
        selected = self._settings.model_timeout_seconds if self._warmed_up else self._settings.model_first_load_timeout_seconds
        try:
            from app.agents.context import remaining_deadline
            remaining = remaining_deadline()
            if remaining is not None:
                selected = min(selected, remaining)
        except ImportError:
            pass
        return selected

    def _chat(self, *, messages, temperature=None, max_output_tokens=None, stop=None,
              json_schema=None, tools=None, think=None, timeout_seconds=None) -> GenerationResult:
        result = self._runtime().chat(
            messages=messages,
            model=self._settings.model_name,
            temperature=self._settings.model_temperature if temperature is None else temperature,
            seed=self._settings.model_seed,
            max_output_tokens=self._settings.model_max_output_tokens if max_output_tokens is None else max_output_tokens,
            context_window=self._settings.model_context_window,
            stop=stop,
            json_schema=json_schema,
            tools=tools,
            think=think,
            timeout_seconds=self._effective_timeout(timeout_seconds),
        )
        self._warmed_up = True
        return result

    def generate_text(self, *, messages: Sequence[ChatMessage], temperature: float | None = None,
                       max_output_tokens: int | None = None, stop: Sequence[str] | None = None,
                       think: bool | None = None, timeout_seconds: float | None = None) -> GenerationResult:
        return self._chat(messages=messages, temperature=temperature, max_output_tokens=max_output_tokens,
                           stop=stop, think=think, timeout_seconds=timeout_seconds)

    def generate_structured(self, *, messages: Sequence[ChatMessage], schema: type[BaseModel],
                             temperature: float | None = None, max_output_tokens: int | None = None,
                             repair_attempts: int | None = None, think: bool | None = None,
                             timeout_seconds: float | None = None) -> StructuredResult:
        json_schema = json_schema_for(schema)
        max_repairs = self._settings.model_structured_repair_attempts if repair_attempts is None else repair_attempts
        conversation = list(messages)
        attempts_used = 0
        while True:
            result = self._chat(messages=conversation, temperature=temperature, max_output_tokens=max_output_tokens,
                                 json_schema=json_schema, think=think, timeout_seconds=timeout_seconds)
            try:
                value = parse_and_validate(result.text, schema)
            except (json.JSONDecodeError, ValidationError) as error:
                if attempts_used >= max_repairs:
                    raise StructuredOutputError(
                        "Model output did not satisfy the required schema after the allotted repair attempts",
                        raw_text=result.text, validation_errors=str(error),
                    ) from error
                attempts_used += 1
                conversation = conversation + [
                    ChatMessage(role="assistant", content=result.text),
                    ChatMessage(role="user", content=(
                        "The previous response did not satisfy the required schema. "
                        f"Validation error: {error}. Respond again with only the corrected JSON object."
                    )),
                ]
                continue
            result.repair_attempts = attempts_used
            try:
                from app.agents.context import record_gateway_repairs
                record_gateway_repairs(attempts_used)
            except ImportError:
                pass
            return StructuredResult(value=value, result=result)

    def generate_with_tools(self, *, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec],
                             tool_choice: Literal["auto", "none"] = "auto", temperature: float | None = None,
                             think: bool | None = None, timeout_seconds: float | None = None) -> GenerationResult:
        effective_tools = tools if tool_choice != "none" else None
        result = self._chat(messages=messages, temperature=temperature, tools=effective_tools,
                             think=think, timeout_seconds=timeout_seconds)
        allowed = {tool.name for tool in tools}
        for call in result.tool_calls:
            if call.name not in allowed:
                raise ToolCallProtocolError(f"Tool call named '{call.name}' is outside the supplied tool specs")
        return result

    def health(self) -> RuntimeHealth:
        return self._runtime().health()

    def list_models(self) -> list[ModelInfo]:
        return self._runtime().list_models()


@lru_cache(maxsize=1)
def get_model_gateway() -> ModelGateway:
    from app.core.config import settings  # deferred: settings' own validation imports this package
    return ModelGateway(settings)
