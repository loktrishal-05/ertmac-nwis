"""Local model gateway: a policy layer (this package) over a swappable runtime
transport (Ollama today, vLLM-compatible later). Agents import only this
package's exports — never a runtime module directly."""
from app.services.model_gateway.errors import (
    ModelConfigurationError,
    ModelGatewayError,
    ModelOutputTruncatedError,
    ModelRuntimeError,
    ModelTimeoutError,
    ModelUnavailableError,
    StructuredOutputError,
    ToolCallProtocolError,
)
from app.services.model_gateway.gateway import ModelGateway, get_model_gateway
from app.services.model_gateway.types import (
    ChatMessage,
    GenerationResult,
    GenerationTimings,
    GenerationUsage,
    ModelInfo,
    RuntimeHealth,
    StructuredResult,
    ToolCall,
    ToolSpec,
)

__all__ = [
    "ChatMessage", "ToolSpec", "ToolCall", "GenerationUsage", "GenerationTimings",
    "ModelInfo", "RuntimeHealth", "GenerationResult", "StructuredResult",
    "ModelGatewayError", "ModelConfigurationError", "ModelUnavailableError", "ModelTimeoutError",
    "ModelRuntimeError", "StructuredOutputError", "ModelOutputTruncatedError", "ToolCallProtocolError",
    "ModelGateway", "get_model_gateway",
]
