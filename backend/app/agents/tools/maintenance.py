"""get_maintenance_history and get_work_order — read-only over Phase 3C's
maintenance query service only."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.agents.evidence import csv_row_evidence
from app.agents.registry import register
from app.agents.tools.base import clamp_limit, clamp_window
from app.services.equipment_tags import normalize_equipment_tag
from app.services.model_gateway.types import ToolSpec
from app.services.structured_queries import maintenance_history, work_order_lookup


def _refs_and_records(records):
    refs = [csv_row_evidence(source_filename=r.citation.source_filename, source_sha256=r.citation.source_sha256,
                              source_row_number=r.citation.source_row_number) for r in records]
    rows = [r.model_dump(mode="json") | {"evidence_id": ref.evidence_id} for r, ref in zip(records, refs)]
    return refs, rows


class GetMaintenanceHistoryArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_tag: str | None = None
    work_order_id: str | None = None
    maintenance_type: str | None = None
    status: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    limit: int = Field(default=50, ge=1, le=2000)


def get_maintenance_history(session, arguments: GetMaintenanceHistoryArguments):
    start, end = clamp_window(arguments.start, arguments.end)
    tag = normalize_equipment_tag(arguments.equipment_tag) if arguments.equipment_tag else None
    records = maintenance_history(
        session, equipment_tag=tag, work_order_id=arguments.work_order_id,
        maintenance_type=arguments.maintenance_type, status=arguments.status,
        start=start, end=end, limit=clamp_limit(arguments.limit),
    )
    refs, rows = _refs_and_records(records)
    return {"records": rows}, refs


class GetWorkOrderArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_order_id: str = Field(min_length=1, max_length=100)


def get_work_order(session, arguments: GetWorkOrderArguments):
    records = work_order_lookup(session, arguments.work_order_id)
    if not records:
        return {"found": False, "records": []}, []
    refs, rows = _refs_and_records(records)
    return {"found": True, "records": rows}, refs


register(
    ToolSpec(
        name="get_maintenance_history",
        description="Read-only lookup of maintenance history rows for an equipment tag, work order, "
                     "maintenance type, status, or a bounded date range.",
        parameters=GetMaintenanceHistoryArguments.model_json_schema(),
    ),
    GetMaintenanceHistoryArguments, get_maintenance_history,
)
register(
    ToolSpec(
        name="get_work_order",
        description="Read-only lookup of maintenance rows for one work order id. An empty result is a "
                     "legitimate 'not found', not an error.",
        parameters=GetWorkOrderArguments.model_json_schema(),
    ),
    GetWorkOrderArguments, get_work_order,
)
