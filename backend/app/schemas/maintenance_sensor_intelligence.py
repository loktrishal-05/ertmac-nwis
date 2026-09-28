"""B2 maintenance & sensor intelligence contracts: bounded-window analysis over
the sensor channels of one equipment tag, cross-linked with maintenance
history. Reuses Phase 3C's SensorFeatureSummary/SensorFeatureThresholds and the
S4 hypothesis contract (MaintenanceHypothesis) rather than redefining either.

Safety shape: observations and contradicting-evidence entries are measured
facts; hypotheses are tentative interpretations that must carry evidence
(MaintenanceHypothesis rejects both evidence-free hypotheses and causal
assertions stated as established). No schema here asserts a diagnosis, and no
field invents a threshold: every threshold check requires a caller-supplied
SensorFeatureThresholds for that channel."""
from datetime import datetime, timedelta, timezone
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.agent_outputs import Citation, MaintenanceHypothesis
from app.schemas.structured import SensorFeatureSummary, SensorFeatureThresholds
from app.agents.evidence import EvidenceRef
from app.core.config import settings


class SensorMaintenanceIntelligenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    equipment_tag: str = Field(min_length=1, max_length=100)
    start: datetime
    end: datetime
    rolling_window: int | None = Field(default=None, ge=2, le=200)
    # Per-channel caller-supplied thresholds keyed by sensor tag. A channel
    # absent from this map gets NO threshold checks -- none are ever invented.
    thresholds: dict[str, SensorFeatureThresholds] = Field(default_factory=dict)
    # Bounded lookback for maintenance-history correlation: a window bound,
    # not a diagnostic threshold.
    maintenance_lookback_days: int = Field(default=30, ge=1, le=365)

    @model_validator(mode="after")
    def valid_range(self):
        self.start = self.start.replace(tzinfo=timezone.utc) if self.start.tzinfo is None else self.start.astimezone(timezone.utc)
        self.end = self.end.replace(tzinfo=timezone.utc) if self.end.tzinfo is None else self.end.astimezone(timezone.utc)
        if self.end <= self.start:
            raise ValueError("end must be after start")
        if self.end - self.start > timedelta(days=settings.agent_tool_max_window_days):
            raise ValueError("sensor window exceeds agent_tool_max_window_days")
        if self.start - datetime.min.replace(tzinfo=timezone.utc) < timedelta(days=self.maintenance_lookback_days):
            raise ValueError("maintenance lookback precedes supported dates")
        for threshold in self.thresholds.values():
            if any(value is not None and not math.isfinite(value) for value in threshold.model_dump().values()):
                raise ValueError("thresholds must be finite")
            if threshold.minimum is not None and threshold.maximum is not None and threshold.minimum > threshold.maximum:
                raise ValueError("minimum must not exceed maximum")
        return self


class ThresholdCrossing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    direction: Literal["above_maximum", "below_minimum"]
    threshold: float
    previous_value: float
    crossing_value: float
    crossed_at: datetime


class AnomalyExcursion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    direction: Literal["above_maximum", "below_minimum"]
    threshold: float
    start: datetime
    end: datetime
    samples: int = Field(ge=1)
    duration_minutes: float = Field(ge=0)
    extreme_value: float


class SustainedRise(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consecutive_increases: int = Field(ge=2)
    samples: int = Field(ge=3)
    start: datetime
    end: datetime
    first_value: float
    last_value: float
    absolute_change: float
    duration_minutes: float = Field(ge=0)


class TrendCorrelation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sensor_tag_a: str
    sensor_tag_b: str
    aligned_samples: int = Field(ge=0)
    # None only when the coefficient is not computable (fewer than 2 aligned
    # samples or zero variance); the reason is carried instead, never guessed.
    pearson_r: float | None = Field(default=None, ge=-1, le=1)
    not_computed_reason: str | None = None

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.pearson_r is None) == (self.not_computed_reason is None):
            raise ValueError("exactly one of pearson_r or not_computed_reason must be set")
        return self


class MaintenanceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    onset_channel: str
    onset_at: datetime
    work_order_id: str | None
    maintenance_type: str | None
    maintenance_date: datetime
    relation: Literal["before_anomaly", "after_anomaly", "at_anomaly"]
    interval_days: float = Field(ge=0)
    evidence_id: str


class IntelligenceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "channel_window_summary", "threshold_crossing", "anomaly_persistence",
        "sustained_rise", "trend_correlation", "maintenance_temporal_relation",
        "threshold_not_supplied", "contradicting_indicator",
    ]
    observation: str
    channel: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class IntelligenceSufficiency(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["SUFFICIENT", "PARTIAL", "INSUFFICIENT"]
    missing_categories: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    meaning: str


class ChannelAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sensor_tag: str
    measurement: str | None = None
    unit: str | None = None
    reading_count: int = Field(ge=0)
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    features: SensorFeatureSummary
    rate_of_change_per_hour: float | None = None
    threshold_crossings: list[ThresholdCrossing] = Field(default_factory=list)
    excursions: list[AnomalyExcursion] = Field(default_factory=list)
    sustained_rise: SustainedRise | None = None
    evidence_id: str
    warnings: list[str] = Field(default_factory=list)


class SensorMaintenanceIntelligenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_tag: str
    window_start: datetime
    window_end: datetime
    maintenance_window_start: datetime
    maintenance_window_end: datetime
    channels: list[ChannelAnalysis]
    correlations: list[TrendCorrelation]
    maintenance_links: list[MaintenanceLink]
    observations: list[IntelligenceObservation]
    contradicting_evidence: list[IntelligenceObservation]
    hypotheses: list[MaintenanceHypothesis]
    recommended_checks: list[str]
    sufficiency: IntelligenceSufficiency
    warnings: list[str] = Field(default_factory=list)
    citations: list[Citation]
    evidence_refs: list[EvidenceRef]
    human_approval_required: bool = True
