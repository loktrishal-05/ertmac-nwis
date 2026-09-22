"""Application observations with explicit limits, never network attestation."""

from typing import Literal
from datetime import datetime
from pydantic import BaseModel


class SovereigntyProof(BaseModel):
    config_version: str = 'phase7-v1'
    timestamp: datetime
    inference_runtime: str
    local_model: str
    inference_endpoint_classification: Literal['local', 'private', 'invalid']
    qdrant_classification: Literal['local', 'private', 'invalid']
    postgresql_classification: Literal['local', 'private', 'invalid']
    data_path_classification: Literal['local_filesystem', 'invalid']
    hosted_ai_configured: bool
    cloud_ai_enabled: bool
    external_ai_calls: int
    local_ai_attempts: int
    observed_since: datetime
    inference_mode: str
    status: Literal['sovereign', 'invalid']
    proof_scope: str = 'application_configuration_and_current_process_gateway_dispatches'
    network_egress_enforced: bool = False
    limitations: str = ('No firewall or physical-network isolation attested. Counters cover this process only, '
                       'reset on restart, and exclude other processes, model-server upstream traffic, and downloads. '
                       'Hostname classification is configuration-based; DNS is checked before model dispatch, '
                       'not pinned. Filesystem mounts are not attested.')
