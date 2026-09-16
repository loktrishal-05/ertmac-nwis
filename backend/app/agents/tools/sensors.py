"""get_sensor_readings, get_latest_reading, compute_sensor_features.

SensorReading.sensor_type stores the MEASUREMENT (vibration,
bearing_temperature, ...) — there is no `measurement` column. The
agent-facing argument is named `measurement`; every read here forwards it as
the `measurement=` keyword straight into structured_queries' service
functions, which map it onto sensor_type internally. Get this wrong and every
sensor query returns an empty set, which an agent would report as "no data
available" with complete confidence."""
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from app.agents.evidence import csv_row_evidence, sensor_window_evidence
from app.agents.registry import register
from app.agents.tools.base import clamp_limit, clamp_window
from app.schemas.structured import SensorFeatureRequest, SensorFeatureThresholds
from app.services.equipment_tags import normalize_equipment_tag
from app.services.model_gateway.types import ToolSpec
from app.services.structured_queries import sensor_features_query, sensor_latest, sensor_readings_query


def _refs_and_readings(readings):
    refs = [csv_row_evidence(source_filename=r.citation.source_filename, source_sha256=r.citation.source_sha256,
                              source_row_number=r.citation.source_row_number) for r in readings]
    rows = [r.model_dump(mode="json") | {"evidence_id": ref.evidence_id} for r, ref in zip(readings, refs)]
    return refs, rows


class GetSensorReadingsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_tag: str | None = None
    sensor_tag: str | None = None
    measurement: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    limit: int = Field(default=200, ge=1, le=2000)


def get_sensor_readings(session, arguments: GetSensorReadingsArguments):
    start, end = clamp_window(arguments.start, arguments.end)
    tag = normalize_equipment_tag(arguments.equipment_tag) if arguments.equipment_tag else None
    readings = sensor_readings_query(
        session, equipment_tag=tag, sensor_tag=arguments.sensor_tag,
        measurement=arguments.measurement, start=start, end=end, limit=clamp_limit(arguments.limit),
    )
    refs, rows = _refs_and_readings(readings)
    return {"readings": rows}, refs


class GetLatestReadingArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_tag: str = Field(min_length=1, max_length=100)
    sensor_tag: str | None = None


def get_latest_reading(session, arguments: GetLatestReadingArguments):
    tag = normalize_equipment_tag(arguments.equipment_tag)
    readings = sensor_latest(session, tag, arguments.sensor_tag)
    refs, rows = _refs_and_readings(readings)
    return {"readings": rows}, refs


class ComputeSensorFeaturesArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_tag: str = Field(min_length=1, max_length=100)
    sensor_tag: str = Field(min_length=1, max_length=100)
    start: datetime
    end: datetime
    rolling_window: int | None = Field(default=None, ge=2, le=200)
    # Caller-supplied and optional. No default is invented here or in config:
    # Phase 3C deliberately has none, and a later threshold loop depends on
    # the value arriving from a cited SOP, not a hardcoded number.
    thresholds: SensorFeatureThresholds | None = None


def compute_sensor_features(session, arguments: ComputeSensorFeaturesArguments):
    start, end = clamp_window(arguments.start, arguments.end)
    request = SensorFeatureRequest(
        equipment_tag=normalize_equipment_tag(arguments.equipment_tag), sensor_tag=arguments.sensor_tag,
        start=start, end=end, rolling_window=arguments.rolling_window,
        thresholds=arguments.thresholds or SensorFeatureThresholds(),
    )
    response = sensor_features_query(session, request, as_of=datetime.now(timezone.utc), write_artifact=False)
    has_provenance = bool(response.provenance)
    ref = sensor_window_evidence(
        source_filename=response.provenance[0].source_filename if has_provenance else "no_matching_readings",
        source_sha256=response.provenance[0].source_sha256 if has_provenance else "0" * 64,
        citation_label=response.citation_label,
        provenance=[p.model_dump(mode="json") for p in response.provenance],
    )
    payload = response.model_dump(mode="json") | {"evidence_id": ref.evidence_id}
    return payload, [ref]


register(
    ToolSpec(
        name="get_sensor_readings",
        description="Read-only lookup of raw sensor readings for an equipment tag / sensor tag / measurement "
                     "and a bounded time window.",
        parameters=GetSensorReadingsArguments.model_json_schema(),
    ),
    GetSensorReadingsArguments, get_sensor_readings,
)
register(
    ToolSpec(
        name="get_latest_reading",
        description="Read-only lookup of the most recent reading per sensor tag for an equipment tag.",
        parameters=GetLatestReadingArguments.model_json_schema(),
    ),
    GetLatestReadingArguments, get_latest_reading,
)
register(
    ToolSpec(
        name="compute_sensor_features",
        description="Read-only deterministic feature and anomaly-observation computation over a bounded "
                     "sensor window. Thresholds are caller-supplied and optional; none are ever invented. "
                     "Observations are factual (e.g. a value crossed a supplied threshold), never diagnoses.",
        parameters=ComputeSensorFeaturesArguments.model_json_schema(),
    ),
    ComputeSensorFeaturesArguments, compute_sensor_features,
)
