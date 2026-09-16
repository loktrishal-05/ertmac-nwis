"""Enumerates the router's 7 routes, the read-only tool registry, and the
model gateway's own health. No route beyond routing itself reasons yet, so
every route reports status "not_implemented"."""
from fastapi import APIRouter

import app.agents.tools  # noqa: F401  (import-time registration side effect)
from app.agents.nodes.stubs import SUB_PHASE
from app.agents.prompts.router import ROUTES
from app.agents.registry import list_tools
from app.schemas.agent import AgentsStatusResponse, RouteStatus, ToolStatus
from app.services.model_gateway import get_model_gateway

router = APIRouter(tags=["agents"])


@router.get("/agents/status", response_model=AgentsStatusResponse)
def agent_status() -> AgentsStatusResponse:
    return AgentsStatusResponse(
        routes=[
            RouteStatus(route=name, description=description, status="not_implemented", sub_phase=SUB_PHASE)
            for name, description in ROUTES
        ],
        tools=[ToolStatus(name=spec.name, description=spec.description) for spec in list_tools()],
        gateway=get_model_gateway().health(),
    )
