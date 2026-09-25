"""Enumerates implemented Phase 4 routes, read-only tools, and gateway health."""
from fastapi import APIRouter

import app.agents.tools  # noqa: F401  (import-time registration side effect)
from app.agents.nodes.stubs import SUB_PHASE
from app.agents.prompts.router import ROUTES
from app.agents.registry import list_tools
from app.schemas.agent import AgentsStatusResponse, RouteStatus, ToolStatus
from app.services.model_gateway import get_model_gateway

router = APIRouter(tags=["agents"])
_ROUTE_PHASE = {"knowledge": "4C", "safety": "4D", "combined_safety_maintenance": "4D/4E",
                "maintenance": "4E", "process_optimization": "4F", "guardrail_refusal": "4B", "clarification": "4B", "shift_handover": "Advanced-B", "environmental_compliance": "Advanced-B"}


@router.get("/agents/status", response_model=AgentsStatusResponse)
def agent_status() -> AgentsStatusResponse:
    return AgentsStatusResponse(
        routes=[
            RouteStatus(route=name, description=description,
                        status="implemented" if name in {"knowledge", "maintenance", "safety", "combined_safety_maintenance", "process_optimization", "shift_handover", "environmental_compliance"} else "guardrail",
                        sub_phase=_ROUTE_PHASE.get(name, SUB_PHASE))
            for name, description in ROUTES + (("shift_handover", "Structured advisory shift handover from local records."), ("environmental_compliance", "Comparison with human-reviewed local environmental rules."))
        ],
        tools=[ToolStatus(name=spec.name, description=spec.description) for spec in list_tools()],
        gateway=get_model_gateway().health(),
    )
