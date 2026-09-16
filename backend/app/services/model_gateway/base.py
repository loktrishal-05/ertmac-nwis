"""The ModelRuntime Protocol every runtime adapter implements.

This file and gateway.py must stay entirely free of any runtime-specific
transport vocabulary (wire field names, endpoint paths, or a runtime's own
name) — that vocabulary belongs only inside its own adapter module. A
source-guard test in tests/test_model_gateway.py enforces this so the
gateway/agent layer never silently couples to one runtime."""
from typing import Protocol, Sequence

from app.services.model_gateway.types import ChatMessage, GenerationResult, ModelInfo, RuntimeHealth, ToolSpec


class ModelRuntime(Protocol):
    name: str

    def chat(
        self,
        *,
        messages: Sequence[ChatMessage],
        model: str,
        temperature: float,
        seed: int | None,
        max_output_tokens: int | None,
        context_window: int | None,
        stop: Sequence[str] | None,
        json_schema: dict | None,
        tools: Sequence[ToolSpec] | None,
        think: bool | None,
        timeout_seconds: float,
    ) -> GenerationResult: ...

    def health(self) -> RuntimeHealth: ...

    def list_models(self) -> list[ModelInfo]: ...
