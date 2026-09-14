"""Declared sovereignty foundation state, not runtime attestation."""

from typing import Literal
from pydantic import BaseModel


class SovereigntyProof(BaseModel):
    external_ai_calls: Literal[0] = 0
    cloud_ai_enabled: Literal[False] = False
    inference_mode: Literal["local_only"] = "local_only"
    status: Literal["sovereign"] = "sovereign"
