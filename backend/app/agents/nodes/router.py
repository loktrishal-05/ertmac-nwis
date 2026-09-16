"""The classification node.

Deterministic fallback lives in CODE here, never in the prompt: a
StructuredOutputError, or a confidence below AGENT_ROUTER_MIN_CONFIDENCE,
routes to the clarification terminal — never to a default agent. A misrouted
query answered confidently by the wrong specialist is worse than an honest
"I need clarification"."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.prompts.router import ROUTER_SYSTEM_PROMPT
from app.core.config import settings
from app.services.model_gateway import ChatMessage, StructuredOutputError, get_model_gateway

Route = Literal[
    "knowledge", "maintenance", "safety", "process_optimization",
    "combined_safety_maintenance", "guardrail_refusal", "clarification",
]


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route: Route
    confidence: float = Field(ge=0, le=1)
    reasoning: str


def router_node(state, gateway=None) -> dict:
    gateway = gateway or get_model_gateway()
    messages = [
        ChatMessage(role="system", content=ROUTER_SYSTEM_PROMPT),
        ChatMessage(role="user", content=state["query"]),
    ]
    try:
        # think=False: the router runs on every single query, and the Phase
        # 4A measurements (docs/phase4a-validation.md) are what justify this.
        result = gateway.generate_structured(messages=messages, schema=RouteDecision, think=False)
    except StructuredOutputError:
        return {
            "route": "clarification", "route_confidence": 0.0,
            "route_reasoning": "Router output did not satisfy the classification schema.",
            "warnings": ["Router fell back to clarification: structured output failed."],
        }
    decision = result.value
    if decision.confidence < settings.agent_router_min_confidence:
        return {
            "route": "clarification", "route_confidence": decision.confidence,
            "route_reasoning": decision.reasoning,
            "warnings": [f"Router confidence {decision.confidence} was below the configured floor "
                         f"{settings.agent_router_min_confidence}; routed to clarification."],
            "_usage": result.result.usage.model_dump(mode="json"),
            "_timings": result.result.timings.model_dump(mode="json"),
        }
    return {
        "route": decision.route, "route_confidence": decision.confidence, "route_reasoning": decision.reasoning,
        "_usage": result.result.usage.model_dump(mode="json"),
        "_timings": result.result.timings.model_dump(mode="json"),
    }
