"""Model-gateway DTOs. Pydantic v2, extra='forbid' everywhere: no caller may
smuggle routing fields (model/base_url/runtime/api_key/endpoint) through here."""
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T", bound=BaseModel)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    name: str | None = None


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    parameters: dict


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    arguments: dict


class GenerationUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class GenerationTimings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_ms: float | None = None
    load_ms: float | None = None
    prompt_eval_ms: float | None = None
    eval_ms: float | None = None
    time_to_first_token_ms: float | None = None


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    digest: str | None = None
    size_bytes: int | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    modified_at: str | None = None


class RuntimeHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runtime: str
    reachable: bool
    runtime_version: str | None = None
    configured_model: str
    configured_model_present: bool
    available_models: list[str] = Field(default_factory=list)
    loaded_models: list[ModelInfo] = Field(default_factory=list)
    detail: str | None = None


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    finish_reason: Literal["stop", "length", "tool_calls", "other"]
    truncated: bool = False
    tool_calls: list[ToolCall] = Field(default_factory=list)
    model: str
    runtime: str
    usage: GenerationUsage
    timings: GenerationTimings
    warnings: list[str] = Field(default_factory=list)
    repair_attempts: int = 0
    raw_response_excerpt: str | None = Field(default=None, max_length=2000)


class StructuredResult(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")
    value: T
    result: GenerationResult
