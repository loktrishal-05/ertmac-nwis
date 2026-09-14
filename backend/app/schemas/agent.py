"""Planned agent status contract."""

from typing import Literal
from pydantic import BaseModel


class AgentStatus(BaseModel):
    name: str
    status: Literal["not_started"] = "not_started"
