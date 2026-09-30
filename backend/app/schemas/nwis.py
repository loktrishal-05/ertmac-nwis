"""Public NWIS contracts. No raw paths, prompts, credentials or reasoning traces."""
from datetime import date, datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

Hazard = Literal['mud_loss','stuck_pipe','kick_or_overpressure','torque_drag','cementing_issue','fishing','npt']
class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra='forbid', allow_inf_nan=False)

class WellOut(Schema):
    id: str
    name: str
    field: str
    latitude: float | None
    longitude: float | None
    operator: str | None
    status: str
    spud_date: date | None
    total_depth_md: float | None
    current_md: float | None
    as_of: datetime | None
    dataset_origin: str

class FormationOut(Schema):
    id: str
    well_id: str
    formation: str
    top_md: float
    bottom_md: float
    top_tvd: float | None
    bottom_tvd: float | None
    top_tvdss: float | None
    bottom_tvdss: float | None
    confidence: float
    source: str
    dataset_origin: str

class EventOut(Schema):
    id: str
    well_id: str
    event_type: str
    start_depth_md: float | None
    end_depth_md: float | None
    tvd: float | None
    tvdss: float | None
    formation: str | None
    severity: str
    observation: str
    cause: str | None
    mitigation: str | None
    outcome: str | None
    npt_hours: float | None
    confidence: float
    source_report_id: str
    source_page: int
    source_span: dict | None
    raw_phrase: str
    verification_state: str
    dataset_origin: str

class MatchOut(Schema):
    offset_well_id: str
    distance_m: float
    distance_km: float
    geographic_score: float
    formation_score: float | None
    depth_score: float | None
    trajectory_score: float | None
    program_score: float | None
    data_quality_score: float
    total_score: float
    depth_basis: str
    weights: dict[str, float]
    algorithm_version: str
    dataset_origin: str
    # Deterministic plain-language reasons derived only from the component scores above (never an LLM).
    explanation: list[str] = []

class TelemetryOut(Schema):
    well_id: str
    timestamp: datetime
    channel: str
    md: float
    tvd: float | None
    value: float | None
    unit: str
    quality: str
    dataset_origin: str

class HazardOut(Schema):
    type: Hazard
    assessment_id: str
    probability: float | None
    confidence: float
    trend: str
    historical_exposure: float | None
    live_anomaly_contribution: float | None
    supporting_offset_wells: list[str]
    top_factors: list[str]
    evidence_ids: list[str]
    data_quality: dict

class RiskOut(Schema):
    well_id: str
    as_of: datetime
    current_md_m: float | None
    current_tvd_m: float | None
    formation: str | None
    lookahead_m: int
    hazards: list[HazardOut]
    dataset_origin: str
    model_version: str
    calibrated: bool = False
    advisory_only: bool = True

class AdvisoryOut(Schema):
    id: str
    assessment_id: str
    text: str
    status: str
    reviewer: UUID | None
    reviewed_at: datetime | None
    feedback: str | None
    model_route: str
    dataset_origin: str
    created_at: datetime

T = TypeVar('T')
class Page(Schema, Generic[T]):
    items: list[T]
    limit: int
    offset: int
    has_more: bool
    as_of: datetime

class DepthValues(Schema):
    md: float | None
    tvd: float | None
    tvdss: float | None

class DepthWindow(Schema):
    lookahead_m: int
    start: DepthValues
    end: DepthValues

class AlignedFormation(Schema):
    interval_id: str
    formation: str
    top: float | None
    base: float | None
    confidence: float
    source: str
    alignment_available: bool

class CasingPoint(Schema):
    md: float = Field(ge=0)
    tvd: float | None = None
    tvdss: float | None = None
    size_in: float | None = Field(default=None,gt=0)
    source: str
    confidence: float | None = Field(default=None,ge=0,le=1)

class CorrelationTrack(Schema):
    well: WellOut
    is_active: bool
    formations: list[AlignedFormation]
    events: list[EventOut]
    casing_points: list[CasingPoint] | None

class ChannelState(Schema):
    channel: str
    known: bool
    unit: str | None
    sample_count: int
    value_count: int
    latest_timestamp: datetime | None
    latest_valid_timestamp: datetime | None
    state: Literal['fresh','stale','unavailable']

class TelemetryPage(Page[TelemetryOut]):
    dataset_origin: str
    source_mode: Literal['replay','historical']
    window_start: datetime
    window_end: datetime
    freshness_reference: datetime
    stale_after_seconds: int = 300
    channels: list[ChannelState]

class CorrelationOut(Schema):
    well_id: str
    as_of: datetime
    dataset_origin: str
    formations: list[FormationOut]
    offset_formations: list[FormationOut]
    events: list[EventOut]
    offsets: list[MatchOut]
    alignment_basis: Literal['md','tvd','tvdss']
    current_bit_depth: DepthValues
    lookahead_window: DepthWindow
    tracks: list[CorrelationTrack]
    warning: str = 'Formation analogs do not establish geological continuity. Missing datums remain unavailable.'

class QueryIn(Schema):
    mode: Literal['nwis_evidence'] = 'nwis_evidence'
    offset_limit: int | None = Field(default=None,ge=1,le=10)
    query: str = Field(min_length=1, max_length=2000)
    well_id: str = Field(default='ACTIVE-01', min_length=1, max_length=80)
    formation: str | None = Field(default=None, max_length=100)
    type: Hazard | None = None
    depth_min: float | None = Field(default=None, ge=-15000, le=15000)
    depth_max: float | None = Field(default=None, ge=-15000, le=15000)
    depth_basis: Literal['md','tvd','tvdss'] = 'tvd'
    lookahead_m: Literal[50,100,150] = 100
    radius_km: float = Field(default=10, gt=0, le=100)
    top_k: int = Field(default=6, ge=1, le=20)
    retrieval: Literal['structured','hybrid'] = 'structured'
    request_id: UUID
    @model_validator(mode='after')
    def ranges(self):
        if self.depth_basis!='tvdss' and any(v is not None and v<0 for v in (self.depth_min,self.depth_max)):
            raise ValueError('Negative depth is supported only for TVDSS')
        if self.depth_min is not None and self.depth_max is not None and self.depth_min > self.depth_max:
            raise ValueError('depth_min exceeds depth_max')
        return self

class QueryOut(Schema):
    mode: Literal['nwis_evidence'] = 'nwis_evidence'
    execution_id: UUID
    status: str
    answer: str
    evidence: list[EventOut]
    offsets: list[MatchOut]
    risk: RiskOut | None
    warnings: list[str]
    model_route: str
    as_of: datetime
    dataset_origin: str

class ReviewIn(Schema):
    status: Literal['acknowledged','dismissed','reviewed']
    reason: str = Field(min_length=5, max_length=1000)

class TermsIn(Schema):
    version: Literal['nwis-advisory-v1']
    accepted: Literal[True]

class TermsOut(Schema):
    version: str = 'nwis-advisory-v1'
    text: str = 'NWIS is an advisory prototype. Synthetic data is not Oil India data. Estimates are uncalibrated; engineering review is required. No rig control is provided.'
    accepted: bool

class AssessmentOut(Schema):
    risk: RiskOut
    advisories: list[AdvisoryOut]

class IngestOut(Schema):
    report_id: str
    status: str
    events: list[EventOut]
    warnings: list[str]
    dataset_origin: str

class RiskEvidenceOut(Schema):
    event: EventOut
    event_at_assessment: EventOut | None
    evidence_chunk_id: str | None
    contribution: float
    reason: str
    source_sha256: str
    source_sha256_at_assessment: str | None
    source_url: str

class AssessmentDetail(Schema):
    assessment_id: str
    well_id: str
    as_of: datetime
    current_md_m: float | None
    formation: str | None
    lookahead_m: int
    model_version: str
    dataset_origin: str
    hazard: HazardOut
    evidence: list[RiskEvidenceOut]
