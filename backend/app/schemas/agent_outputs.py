"""S1-S7 structured agent-output contracts, shared across Phases 4C-4F.

Field lists are derived only from docs/model-evaluation-spec.md lines 91-121
("## 4. Expected output schemas") -- never from that file's case table
further down. See docs/phase4-decisions.md D-002 and D-005.

Defined once here (rather than per sub-phase) so every specialist agent
validates against the identical shape, and so the benchmark-spec section is
read exactly once across the whole autonomous run rather than once per
sub-phase.

Every model uses extra="forbid": no specialist agent may smuggle an
undocumented field past its own schema. `citations`/tag/observation
evidence_id fields are validated for EXISTENCE against gathered evidence by
app.agents.enforcement, never by the schema itself (a schema cannot know at
class-definition time what evidence a future turn will gather)."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    locator: str
    claim: str


# --- S1: Grounded answer -----------------------------------------------

class GroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    observations: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
    human_approval_required: bool = False


# --- S3: Equipment tags --------------------------------------------------

class EquipmentTag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_text: str
    normalized_tag: str | None
    equipment_type: str | None
    evidence_id: str
    confidence: float = Field(ge=0, le=1)
    status: Literal["verified", "ambiguous", "unverified"]


class EquipmentTags(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: list[EquipmentTag] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# --- S4: Maintenance assessment ------------------------------------------

class MaintenanceHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def must_carry_evidence(self):
        if not self.supporting_evidence and not self.contradicting_evidence:
            raise ValueError(
                "a hypothesis must carry supporting_evidence or contradicting_evidence; "
                "a hypothesis with neither is rejected structurally, not merely warned about"
            )
        return self


class MaintenanceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_tag: str
    observations: list[str] = Field(default_factory=list)
    hypotheses: list[MaintenanceHypothesis] = Field(default_factory=list)
    recommended_checks: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0, le=1)
    human_approval_required: bool = False


# --- S5: Refusal / insufficient evidence ---------------------------------

class Refusal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["refused", "insufficient_evidence", "clarification_required"]
    reason: str
    missing_evidence: list[str] = Field(default_factory=list)
    safe_next_step: str
    citations: list[Citation] = Field(default_factory=list)
    human_approval_required: bool = False


# --- S6: Sensor interpretation --------------------------------------------

class SensorObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str
    value_or_trend: str
    evidence_id: str


class SensorInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_tag: str
    time_window: str
    observations: list[SensorObservation] = Field(default_factory=list)
    anomaly_status: Literal["normal", "warning", "critical", "indeterminate"]
    hypotheses: list[MaintenanceHypothesis] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    human_approval_required: bool = False


# --- S7: Action-adjacent recommendation -----------------------------------

class ProposedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    action_class: Literal["informational", "inspection", "process_change", "isolation", "shutdown"]
    approval_status: Literal["not_required", "required", "approved"]


class ActionRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    evidence_basis: list[str] = Field(default_factory=list)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    human_approval_required: bool = False
