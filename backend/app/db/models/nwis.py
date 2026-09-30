"""SIH26121 additive domain. Depths are metres; missing measurements remain NULL."""
from datetime import date, datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType
from app.db.base import Base, CreatedAtMixin
from app.db.models.agent_run import JSONVariant

HAZARDS = ("mud_loss", "stuck_pipe", "kick_or_overpressure", "torque_drag", "cementing_issue", "fishing", "npt")

class Geography(UserDefinedType):
    cache_ok = True
    def __init__(self, *args):
        pass
    def get_col_spec(self, **kw):
        return 'public.geography(Point,4326)'

from sqlalchemy.dialects.postgresql.base import ischema_names
ischema_names.setdefault('geography', Geography)
ischema_names.setdefault('public.geography', Geography)

class Origin:
    dataset_origin: Mapped[str] = mapped_column(String(100))

class Well(Origin, CreatedAtMixin, Base):
    __tablename__ = "nwis_wells"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    field: Mapped[str] = mapped_column(String(120))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location: Mapped[str | None] = mapped_column(Geography().with_variant(Text(), 'sqlite'))
    operator: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30))
    spud_date: Mapped[date | None] = mapped_column(Date)
    total_depth_md: Mapped[float | None] = mapped_column(Float)
    current_md: Mapped[float | None] = mapped_column(Float)
    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    program: Mapped[dict | None] = mapped_column(JSONVariant)
    access_scope: Mapped[str] = mapped_column(String(20), default="internal")
    __table_args__ = (CheckConstraint("latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180", name="coordinates"),
                      Index('ix_nwis_wells_location', 'location', postgresql_using='gist'))

class WellTrajectoryPoint(Origin, Base):
    __tablename__ = "nwis_trajectory_points"
    well_id: Mapped[str] = mapped_column(ForeignKey("nwis_wells.id"), primary_key=True)
    md: Mapped[float] = mapped_column(Float, primary_key=True)
    tvd: Mapped[float | None] = mapped_column(Float)
    tvdss: Mapped[float | None] = mapped_column(Float)
    inclination: Mapped[float | None] = mapped_column(Float)
    azimuth: Mapped[float | None] = mapped_column(Float)
    northing: Mapped[float | None] = mapped_column(Float)
    easting: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(200))
    quality: Mapped[float] = mapped_column(Float)
    __table_args__ = (CheckConstraint("md >= 0 AND quality BETWEEN 0 AND 1", name="trajectory_values"),)

class FormationInterval(Origin, Base):
    __tablename__ = "nwis_formation_intervals"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    well_id: Mapped[str] = mapped_column(ForeignKey("nwis_wells.id"), index=True)
    formation: Mapped[str] = mapped_column(String(100), index=True)
    top_md: Mapped[float] = mapped_column(Float)
    bottom_md: Mapped[float] = mapped_column(Float)
    top_tvd: Mapped[float | None] = mapped_column(Float)
    bottom_tvd: Mapped[float | None] = mapped_column(Float)
    top_tvdss: Mapped[float | None] = mapped_column(Float)
    bottom_tvdss: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(200))
    __table_args__ = (CheckConstraint("top_md >= 0 AND bottom_md > top_md AND confidence BETWEEN 0 AND 1", name="formation_values"),)

class DrillingReport(Origin, CreatedAtMixin, Base):
    __tablename__ = "nwis_drilling_reports"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    well_id: Mapped[str] = mapped_column(ForeignKey("nwis_wells.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    report_date: Mapped[date | None] = mapped_column(Date)
    file_hash: Mapped[str] = mapped_column(String(64))
    extraction_status: Mapped[str] = mapped_column(String(30))
    parser_version: Mapped[str] = mapped_column(String(50))
    __table_args__ = (UniqueConstraint("well_id", "file_hash"), CheckConstraint("type IN ('WCR','DDR','incident','program')", name="report_type"))

class DrillingEvent(Origin, Base):
    __tablename__ = "nwis_drilling_events"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    well_id: Mapped[str] = mapped_column(ForeignKey("nwis_wells.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    start_depth_md: Mapped[float | None] = mapped_column(Float)
    end_depth_md: Mapped[float | None] = mapped_column(Float)
    tvd: Mapped[float | None] = mapped_column(Float)
    tvdss: Mapped[float | None] = mapped_column(Float)
    formation: Mapped[str | None] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(30))
    observation: Mapped[str] = mapped_column(Text)
    cause: Mapped[str | None] = mapped_column(Text)
    mitigation: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text)
    npt_hours: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    source_report_id: Mapped[str] = mapped_column(ForeignKey("nwis_drilling_reports.id"))
    source_page: Mapped[int] = mapped_column(Integer)
    source_span: Mapped[dict | None] = mapped_column(JSONVariant)
    raw_phrase: Mapped[str] = mapped_column(Text)
    verification_state: Mapped[str] = mapped_column(String(30), default="unverified")
    __table_args__ = (CheckConstraint("confidence BETWEEN 0 AND 1 AND source_page > 0 AND (npt_hours IS NULL OR npt_hours >= 0) AND (start_depth_md IS NULL OR start_depth_md >= 0) AND (end_depth_md IS NULL OR end_depth_md >= start_depth_md)", name="event_values"),)

class TelemetrySample(Origin, Base):
    __tablename__ = "nwis_telemetry_samples"
    well_id: Mapped[str] = mapped_column(ForeignKey("nwis_wells.id"), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    channel: Mapped[str] = mapped_column(String(50), primary_key=True)
    md: Mapped[float] = mapped_column(Float)
    tvd: Mapped[float | None] = mapped_column(Float)
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(30))
    quality: Mapped[str] = mapped_column(String(30))

class OffsetWellMatch(Origin, Base):
    __tablename__ = "nwis_offset_matches"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    active_well_id: Mapped[str] = mapped_column(ForeignKey("nwis_wells.id"))
    offset_well_id: Mapped[str] = mapped_column(ForeignKey("nwis_wells.id"))
    geographic_score: Mapped[float] = mapped_column(Float)
    formation_score: Mapped[float | None] = mapped_column(Float)
    depth_score: Mapped[float | None] = mapped_column(Float)
    trajectory_score: Mapped[float | None] = mapped_column(Float)
    program_score: Mapped[float | None] = mapped_column(Float)
    data_quality_score: Mapped[float] = mapped_column(Float)
    total_score: Mapped[float] = mapped_column(Float)
    algorithm_version: Mapped[str] = mapped_column(String(50))

class RiskAssessment(Origin, Base):
    __tablename__ = "nwis_risk_assessments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    well_id: Mapped[str] = mapped_column(ForeignKey("nwis_wells.id"), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_md: Mapped[float | None] = mapped_column(Float)
    formation: Mapped[str | None] = mapped_column(String(100))
    lookahead_m: Mapped[int] = mapped_column(Integer)
    hazard_type: Mapped[str] = mapped_column(String(40))
    probability: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    trend: Mapped[str] = mapped_column(String(30))
    model_version: Mapped[str] = mapped_column(String(50))
    snapshot: Mapped[dict] = mapped_column(JSONVariant)
    __table_args__ = (CheckConstraint("(probability IS NULL OR probability BETWEEN 0 AND 1) AND confidence BETWEEN 0 AND 1", name="risk_values"),)

class RiskEvidence(Origin, Base):
    __tablename__ = "nwis_risk_evidence"
    assessment_id: Mapped[str] = mapped_column(ForeignKey("nwis_risk_assessments.id"), primary_key=True)
    drilling_event_id: Mapped[str] = mapped_column(ForeignKey("nwis_drilling_events.id"), primary_key=True)
    evidence_chunk_id: Mapped[str | None] = mapped_column(String(100))
    offset_well_id: Mapped[str] = mapped_column(ForeignKey("nwis_wells.id"))
    contribution: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)

class DrillingAdvisory(Origin, CreatedAtMixin, Base):
    __tablename__ = "nwis_advisories"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("nwis_risk_assessments.id"))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending_review")
    reviewer: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feedback: Mapped[str | None] = mapped_column(Text)
    model_route: Mapped[str] = mapped_column(String(80), default="deterministic-evidence-template")

class AlertState(Base):
    __tablename__ = "nwis_alert_states"
    well_id: Mapped[str] = mapped_column(ForeignKey("nwis_wells.id"), primary_key=True)
    hazard: Mapped[str] = mapped_column(String(40), primary_key=True)
    interval: Mapped[int] = mapped_column(Integer, primary_key=True)
    consecutive: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(default=False)
    last_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class TermsAcceptance(Base):
    __tablename__ = "nwis_terms_acceptances"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    version: Mapped[str] = mapped_column(String(50), primary_key=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

NWIS_TABLES = [Well, WellTrajectoryPoint, FormationInterval, DrillingReport, DrillingEvent, TelemetrySample,
              OffsetWellMatch, RiskAssessment, RiskEvidence, DrillingAdvisory, AlertState, TermsAcceptance]
