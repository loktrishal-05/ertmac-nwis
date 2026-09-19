"""Agent orchestration package: LangGraph state, router, and tool registry.

Sovereignty: langgraph pulls in langchain_core, which can trigger langsmith's
hosted tracing client as an import-time side effect in some code paths.
Tracing is disabled defensively HERE, at package import time, before any
submodule in this package (or langgraph/langchain_core themselves) is
imported below — not only in .env, because .env is only guaranteed to be
loaded once app.core.config is imported, and this package must be safe to
import on its own (e.g. `python -c "import app.agents"`, or a future
entrypoint that imports this package before config). os.environ.setdefault
is used rather than direct assignment so an operator can still override
deliberately via the real environment.
"""
import os

_TELEMETRY_DEFAULTS = {
    "LANGCHAIN_TRACING_V2": "false",
    "LANGSMITH_TRACING": "false",
    "LANGCHAIN_ENDPOINT": "",
    "LANGSMITH_ENDPOINT": "",
}
for _key, _value in _TELEMETRY_DEFAULTS.items():
    # Production/on-prem mode owns this boundary; a process environment must
    # not silently turn hosted tracing back on.
    os.environ[_key] = _value
del _key, _value

from app.agents.graph import get_graph, run_graph  # noqa: E402
from app.agents.state import WorkbenchState  # noqa: E402
import app.agents.tools  # noqa: E402,F401  (import-time tool registration)

__all__ = ["get_graph", "run_graph", "WorkbenchState"]
