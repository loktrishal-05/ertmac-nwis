"""Request-scoped advisory context used by read-only tool adapters."""
from contextvars import ContextVar
from time import monotonic

_access_scope: ContextVar[str] = ContextVar("workbench_access_scope", default="internal")
_deadline: ContextVar[float | None] = ContextVar("workbench_agent_deadline", default=None)
_tool_records: ContextVar[list[dict] | None] = ContextVar("workbench_tool_records", default=None)
_gateway_repairs: ContextVar[list[int] | None] = ContextVar("workbench_gateway_repairs", default=None)


def set_access_scope(scope: str):
    return _access_scope.set(scope or "internal")


def reset_access_scope(token) -> None:
    _access_scope.reset(token)


def get_access_scope() -> str:
    return _access_scope.get()


def set_deadline(seconds: float):
    return _deadline.set(monotonic() + seconds)


def reset_deadline(token) -> None:
    _deadline.reset(token)


def remaining_deadline() -> float | None:
    value = _deadline.get()
    return max(value - monotonic(), 0.0) if value is not None else None


def set_tool_records(records: list[dict]):
    return _tool_records.set(records)


def reset_tool_records(token) -> None:
    _tool_records.reset(token)


def tool_records() -> list[dict]:
    records = _tool_records.get()
    return records if records is not None else []


def set_gateway_repairs(counter: list[int]):
    return _gateway_repairs.set(counter)


def reset_gateway_repairs(token) -> None:
    _gateway_repairs.reset(token)


def gateway_repairs() -> int:
    counter = _gateway_repairs.get()
    return counter[0] if counter else 0


def record_gateway_repairs(attempts: int) -> None:
    counter = _gateway_repairs.get()
    if counter is not None:
        counter[0] += attempts
