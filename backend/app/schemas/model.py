"""Read-only /models/status contract. Never exposes MODEL_BASE_URL, a
credential, or prompt text — there is no generation endpoint in Phase 4A."""
from pydantic import BaseModel, ConfigDict

from app.services.model_gateway.types import ModelInfo


class ModelSettingsInForce(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temperature: float
    seed: int
    context_window: int
    max_output_tokens: int


class ModelStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runtime: str
    reachable: bool
    runtime_version: str | None
    configured_model: str
    configured_model_present: bool
    available_models: list[str]
    loaded_models: list[ModelInfo]
    settings: ModelSettingsInForce
    detail: str | None = None
