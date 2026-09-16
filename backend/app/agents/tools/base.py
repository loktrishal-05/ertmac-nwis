"""Shared tool-adapter helpers: argument bounding against config limits.

Every window/limit argument that reaches a Phase 3C query must be clamped
here first. Phase 3C's read services load matching rows into memory with no
pagination — an agent-chosen unbounded range is a denial-of-service on our
own backend, not merely an inefficiency."""
from datetime import datetime, timedelta
from typing import Protocol

from app.core.config import settings


class ToolAdapter(Protocol):
    def __call__(self, session, arguments) -> tuple[dict, list]: ...


def clamp_limit(limit: int) -> int:
    return min(limit, settings.structured_query_max_limit)


def clamp_window(start: datetime | None, end: datetime | None) -> tuple[datetime | None, datetime | None]:
    """Bounds an agent-chosen [start, end] window to AGENT_TOOL_MAX_WINDOW_DAYS,
    clamping the end forward from start. Either bound may be None (an
    unbounded query on one side is still bounded by the query's own default
    limit, not by this function)."""
    if start is None or end is None:
        return start, end
    max_span = timedelta(days=settings.agent_tool_max_window_days)
    if end - start > max_span:
        end = start + max_span
    return start, end
