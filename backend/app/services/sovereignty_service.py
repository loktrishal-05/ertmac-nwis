"""Configuration-derived proof plus real gateway process observations."""

from datetime import datetime, timezone
from app.core.config import settings
from app.core.locality import classify_http_url, classify_database, local_filesystem
from app.schemas.sovereignty import SovereigntyProof
from app.services.model_gateway.registry import validate_model_url, validate_model_name
from app.services.model_gateway.observations import snapshot


def get_sovereignty_proof() -> SovereigntyProof:
    inference = classify_http_url(settings.model_base_url)
    try:
        validate_model_url(settings.model_base_url, settings.model_allowed_hosts_set)
        validate_model_name(settings.model_name)
    except ValueError:
        inference = 'invalid'
    hosted = inference == 'invalid' or settings.model_runtime not in ('ollama', 'vllm')
    qdrant = classify_http_url(settings.qdrant_url)
    postgres = classify_database(settings.database_url)
    files = 'local_filesystem' if local_filesystem(settings.data_root) and local_filesystem(settings.model_root) else 'invalid'
    observations = snapshot()
    valid = not hosted and 'invalid' not in (qdrant, postgres, files) and observations['external_ai_calls'] == 0
    return SovereigntyProof(timestamp=datetime.now(timezone.utc), inference_runtime=settings.model_runtime,
        local_model=settings.model_name, inference_endpoint_classification=inference,
        qdrant_classification=qdrant, postgresql_classification=postgres, data_path_classification=files,
        hosted_ai_configured=hosted, cloud_ai_enabled=hosted, inference_mode='local_only' if not hosted else 'invalid',
        status='sovereign' if valid else 'invalid', **observations)
