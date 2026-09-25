"""Bounded local operational requests; no client authority fields."""
from datetime import timedelta
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator

class NoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    equipment_tag: str = Field(min_length=1, max_length=100)
    unit: str | None = Field(default=None, max_length=100)
    text: str = Field(min_length=1, max_length=4000)
    access_scope: Literal["internal"] = "internal"

class HandoverInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_tag: str = Field(min_length=1, max_length=100)
    start: AwareDatetime
    end: AwareDatetime
    access_scope: Literal["internal"] = "internal"
    @model_validator(mode="after")
    def bounded(self):
        if not timedelta(0) < self.end - self.start <= timedelta(hours=72):
            raise ValueError("Shift period must be positive and at most 72 hours")
        return self

class ComplianceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reading_id: UUID
    rule_ids: list[UUID] = Field(default_factory=list, max_length=10)
    access_scope: Literal["internal"] = "internal"

class LocalLimit(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    parameter: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=50)
    equipment_tag: str = Field(min_length=1, max_length=100)
    upper_limit: float
    valid_from: AwareDatetime
    valid_to: AwareDatetime
    averaging_period: Literal["instantaneous"]
    @model_validator(mode="after")
    def valid_interval(self):
        if self.valid_to <= self.valid_from: raise ValueError("Rule validity interval is invalid")
        return self
