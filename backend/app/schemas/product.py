from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class SpeechInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_language: str = Field(default="en", min_length=1, max_length=20, pattern=r"^[A-Za-z-]+$")


class TranscriptionInput(SpeechInput):
    audio_base64: str = Field(min_length=1, max_length=5592408)
    mime_type: Literal["audio/wav", "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4"]


class SynthesisInput(SpeechInput):
    text: str = Field(min_length=1, max_length=10000)


AutomationKind = Literal["shift_handover_reminder", "knowledge_gap_notification", "pending_review_notification",
    "environmental_review_reminder", "maintenance_advisory_notification", "report_delivery", "audit_summary"]


class AutomationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nonce: UUID
    timestamp: int = Field(strict=True, ge=0)
    kind: AutomationKind
