"""Planned agents; independent of database records."""

from fastapi import APIRouter
from app.schemas.agent import AgentStatus

router = APIRouter(tags=["agents"])


@router.get("/agents/status", response_model=list[AgentStatus])
def agent_status() -> list[AgentStatus]:
    return [AgentStatus(name=name) for name in (
        "Orchestrator Agent", "Knowledge Agent", "Safety Agent",
        "Maintenance Agent", "Guardrail Agent",
    )]
