"""Government/Indian language resource policy. A registry and a gate, never an authority source.

Confidential plant/company data may only reach LOCAL_APPROVED resources. External
public services (BHASHINI) are PUBLIC_EXTERNAL_OPTIONAL: off by default, and even
when enabled only permitted for explicitly public data. This build ships no
external speech client, so no code path can send data to BHASHINI.
"""
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import settings

Classification = Literal["LOCAL_APPROVED", "PUBLIC_EXTERNAL_OPTIONAL", "DISABLED_FOR_CONFIDENTIAL_DATA"]
DataClass = Literal["CONFIDENTIAL", "PUBLIC"]
LOCAL_STT, LOCAL_TTS, BHASHINI = "Configured local STT runtime", "Configured local TTS runtime", "BHASHINI public language APIs"


class PolicyDenied(ValueError):
    pass


class LanguageResource(BaseModel):
    """One operator-reviewed entry; unreviewed entries stay DISABLED_FOR_CONFIDENTIAL_DATA."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=100)   # e.g. "AIKosh", "BHASHINI", "local"
    source: str = Field(min_length=1, max_length=500)     # catalogue URL or local path, reference only
    license: str = Field(min_length=1, max_length=200)
    intended_use: str = Field(min_length=1, max_length=500)
    # local_runtime: the configured loopback/private endpoint; local_downloaded: a pinned artifact.
    deployment: Literal["local_runtime", "local_downloaded", "external_api"]
    classification: Classification = "DISABLED_FOR_CONFIDENTIAL_DATA"
    approved_by: str | None = Field(default=None, max_length=200)
    artifact_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def approval_is_explicit(self):
        if self.classification == "LOCAL_APPROVED":
            if self.deployment == "external_api":
                raise ValueError("An external API cannot be LOCAL_APPROVED")
            if not self.approved_by or (self.deployment == "local_downloaded" and not self.artifact_sha256):
                raise ValueError("LOCAL_APPROVED requires an approver, and a SHA-256 for a downloaded artifact")
        return self


def builtin():
    return [
        LanguageResource(name=LOCAL_STT, provider="local", source="STT_URL (loopback/private only)",
            license="operator-provisioned", intended_use="Confidential speech-to-text", deployment="local_runtime",
            classification="LOCAL_APPROVED", approved_by="workbench locality policy"),
        LanguageResource(name=LOCAL_TTS, provider="local", source="TTS_URL (loopback/private only)",
            license="operator-provisioned", intended_use="Confidential text-to-speech", deployment="local_runtime",
            classification="LOCAL_APPROVED", approved_by="workbench locality policy"),
        LanguageResource(name=BHASHINI, provider="BHASHINI", source="https://bhashini.gov.in",
            license="Government of India service terms (operator must review)",
            intended_use="Optional public/non-confidential ASR, TTS and translation",
            deployment="external_api", classification="PUBLIC_EXTERNAL_OPTIONAL"),
    ]


def registry(config=None):
    """Built-in entries plus the operator JSON registry (a list of LanguageResource objects)."""
    config = config or settings
    entries = builtin()
    if config.language_resource_registry:
        data = json.loads(Path(config.language_resource_registry).read_text(encoding="utf-8"))
        entries += [LanguageResource.model_validate(item) for item in data]
    return entries


def permitted(resource, data_class: DataClass, config=None):
    config = config or settings
    if resource.classification == "LOCAL_APPROVED":
        return True
    if resource.classification == "PUBLIC_EXTERNAL_OPTIONAL":
        enabled = config.bhashini_enabled if resource.provider == "BHASHINI" else False
        return data_class == "PUBLIC" and enabled
    return False  # DISABLED_FOR_CONFIDENTIAL_DATA, including every unreviewed entry.


def speech_provider(kind: Literal["stt", "tts"], data_class: DataClass = "CONFIDENTIAL", provider="local", config=None):
    """Return the provenance for a permitted speech provider, or raise PolicyDenied."""
    config = config or settings
    name = {"local": {"stt": LOCAL_STT, "tts": LOCAL_TTS}[kind], "BHASHINI": BHASHINI}.get(provider)
    resource = next((r for r in registry(config) if r.name == name), None)
    if resource is None or not permitted(resource, data_class, config):
        raise PolicyDenied(f"{provider} is not permitted for {data_class.lower()} {kind}")
    if resource.deployment == "external_api":
        # Permitted by policy for public data, but no external client is shipped in this build.
        raise PolicyDenied("External speech client is not implemented; use the local runtime")
    return {"provider": resource.provider, "resource": resource.name, "classification": resource.classification,
            "data_classification": data_class}


def summary(config=None):
    config = config or settings
    return [{"name": r.name, "provider": r.provider, "classification": r.classification, "deployment": r.deployment,
             "license": r.license, "confidential_eligible": r.classification == "LOCAL_APPROVED",
             "enabled_for_public": permitted(r, "PUBLIC", config)} for r in registry(config)]
