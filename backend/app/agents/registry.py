"""The tool registry — the safety boundary.

Enumerable: list_tools() returns the complete, closed set. Closed: get_tool()
raises on an unregistered name; there is no dynamic registration path and no
plugin loader. Registration happens only via explicit register() calls made
at import time by app/agents/tools/*.py — never at runtime from external
input."""
from pydantic import BaseModel

from app.services.model_gateway.types import ToolSpec
from app.agents.context import get_access_scope
from app.agents.context import tool_records
from time import perf_counter
from app.services.execution_observability import record_tool


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
        started = perf_counter()
        try:
            values = dict(raw_arguments)
            if "access_scope" in self.argument_model.model_fields and "access_scope" not in values:
                values["access_scope"] = get_access_scope()
            arguments = self.argument_model.model_validate(values)
            from app.services.durable_execution import durable_tool
            result = durable_tool(self.spec.name, arguments.model_dump(mode="json"),
                                  lambda: self.adapter(session, arguments))
            payload, refs = result if isinstance(result, tuple) and len(result) == 2 else (result, [])
            tool_records().append({"tool_name": self.spec.name, "arguments": values,
                                   "evidence_ids": [ref.evidence_id for ref in refs],
                                   "duration_ms": (perf_counter() - started) * 1000,
                                   "warnings": list(payload.get("warnings", [])) if isinstance(payload, dict) else [],
                                   "error": None})
            record_tool(self.spec.name, (perf_counter() - started) * 1000, False)
            return result
        except Exception as error:
            record_tool(self.spec.name, (perf_counter() - started) * 1000, True)
            if "arguments" not in locals():
                raise ToolArgumentError(f"Invalid arguments for tool '{self.spec.name}': {error}") from error
            tool_records().append({"tool_name": self.spec.name, "arguments": dict(raw_arguments),
                                   "evidence_ids": [], "duration_ms": (perf_counter() - started) * 1000,
                                   "warnings": [], "error": str(error)})
            raise


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
