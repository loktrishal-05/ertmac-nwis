"""GET /agents/status contract: enumerates the 7 routes, the read-only tool
registry, and the model gateway's own health — never a base URL, API key, or
prompt body."""
from pydantic import BaseModel, ConfigDict

from app.services.model_gateway.types import RuntimeHealth


class RouteStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route: str
    description: str
    status: str
    sub_phase: str


class ToolStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    read_only: bool = True


class AgentsStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    routes: list[RouteStatus]
    tools: list[ToolStatus]
    gateway: RuntimeHealth
