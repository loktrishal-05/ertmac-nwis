"""The tool registry — the safety boundary.

Enumerable: list_tools() returns the complete, closed set. Closed: get_tool()
raises on an unregistered name; there is no dynamic registration path and no
plugin loader. Registration happens only via explicit register() calls made
at import time by app/agents/tools/*.py — never at runtime from external
input."""
from pydantic import BaseModel

from app.services.model_gateway.types import ToolSpec


class ToolArgumentError(ValueError):
    """A tool's arguments failed Pydantic validation (extra='forbid' or a
    type/range check). Never a silently-dropped field."""


class ToolNotFoundError(KeyError):
    """An unregistered tool name was requested."""


class RegisteredTool:
    def __init__(self, spec: ToolSpec, argument_model: type[BaseModel], adapter):
        self.spec = spec
        self.argument_model = argument_model
        self.adapter = adapter

    def invoke(self, session, raw_arguments: dict):
        try:
            arguments = self.argument_model.model_validate(raw_arguments)
        except Exception as error:
            raise ToolArgumentError(f"Invalid arguments for tool '{self.spec.name}': {error}") from error
        return self.adapter(session, arguments)


_REGISTRY: dict[str, RegisteredTool] = {}


def register(spec: ToolSpec, argument_model: type[BaseModel], adapter) -> None:
    if spec.name in _REGISTRY:
        raise RuntimeError(f"Tool '{spec.name}' is already registered")
    _REGISTRY[spec.name] = RegisteredTool(spec, argument_model, adapter)


def list_tools() -> list[ToolSpec]:
    return [tool.spec for tool in _REGISTRY.values()]


def get_tool(name: str) -> RegisteredTool:
    if name not in _REGISTRY:
        raise ToolNotFoundError(f"Unregistered tool: {name!r}")
    return _REGISTRY[name]


def invoke_tool(name: str, session, raw_arguments: dict):
    return get_tool(name).invoke(session, raw_arguments)
