"""Maintenance/sensor structured-data contracts. No diagnoses; observations only."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class MaintenanceIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_path: str = Field(min_length=1, max_length=500, description="CSV path relative to data/raw/maintenance")
    facility_id: str | None = Field(default=None, max_length=100)
    synthetic: bool = False


class SensorIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_path: str = Field(min_length=1, max_length=500, description="CSV path relative to data/raw/sensors")
    facility_id: str | None = Field(default=None, max_length=100)
    synthetic: bool = False


class StructuredIngestResponse(BaseModel):
    source_id: UUID
    source_type: Literal["maintenance", "sensor"]
    filename: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["ingested", "duplicate"]
    row_count: int = Field(ge=0)
    rejected_row_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class StructuredCitation(BaseModel):
    source_filename: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_row_number: int = Field(ge=1)


class MaintenanceRecordOut(BaseModel):
    id: UUID
    equipment_tag: str
    raw_equipment_tag: str
    work_order_id: str | None
    maintenance_type: str | None
    failure_mode: str | None
    maintenance_date: datetime | None
    description: str | None
    downtime_hours: float | None
    parts_replaced: str | None
    technician_notes: str | None
    status: str | None
    ingested_at: datetime
    citation: StructuredCitation


class MaintenanceHistoryResponse(BaseModel):
    warnings: list[str] = Field(default_factory=list)
    results: list[MaintenanceRecordOut]


class SensorReadingOut(BaseModel):
    id: UUID
    equipment_tag: str
    sensor_tag: str
    measurement: str
    value: float
    unit: str | None
    quality: str | None
    timestamp: datetime
    ingested_at: datetime
    citation: StructuredCitation


class SensorReadingsResponse(BaseModel):
    warnings: list[str] = Field(default_factory=list)
    results: list[SensorReadingOut]


class SensorFeatureThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maximum: float | None = None
    minimum: float | None = None
    max_absolute_change: float | None = None
    expected_interval_minutes: float | None = Field(default=None, gt=0)
    stale_after_minutes: float | None = Field(default=None, gt=0)


class SensorFeatureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    equipment_tag: str = Field(min_length=1, max_length=100)
    sensor_tag: str = Field(min_length=1, max_length=100)
    start: datetime
    end: datetime
    rolling_window: int | None = Field(default=None, ge=2, le=200)
    thresholds: SensorFeatureThresholds = Field(default_factory=SensorFeatureThresholds)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class SensorFeatureSummary(BaseModel):
    count: int = Field(ge=0)
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    median: float | None = None
    stdev: float | None = None
    first_value: float | None = None
    last_value: float | None = None
    absolute_change: float | None = None
    percentage_change: float | None = None
    rolling_mean: list[float] | None = None
    slope: float | None = None


class AnomalyObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "threshold_exceeded", "threshold_below", "sudden_change", "missing_samples",
        "stale_sensor", "bad_quality", "relative_increase", "relative_decrease",
    ]
    observation: str
    evidence: dict


class SensorFeatureResponse(BaseModel):
    equipment_tag: str
    sensor_tag: str
    measurement: str | None
    unit: str | None
    window_start: datetime
    window_end: datetime
    features: SensorFeatureSummary
    observations: list[AnomalyObservation]
    warnings: list[str] = Field(default_factory=list)
    citation_label: str
    provenance: list[StructuredCitation]
