"""Read-only local model runtime status. GET /models/status is the only route
Phase 4A adds; there is no generation endpoint."""
import logging
from fastapi import APIRouter, HTTPException
from app.core.config import settings
from app.schemas.model import ModelSettingsInForce, ModelStatusResponse
from app.services.model_gateway import ModelGatewayError, get_model_gateway

router = APIRouter(tags=["models"])
logger = logging.getLogger(__name__)


@router.get("/models/status", response_model=ModelStatusResponse)
def model_status() -> ModelStatusResponse:
    try:
        health = get_model_gateway().health()
    except ModelGatewayError as error:
        logger.error("Model gateway health check failed: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Model runtime unavailable; check MODEL_RUNTIME/MODEL_BASE_URL and that the runtime is running.") from error
    if not health.reachable:
        raise HTTPException(status_code=503, detail="Model runtime unreachable.")
    return ModelStatusResponse(
        runtime=health.runtime, reachable=health.reachable, runtime_version=health.runtime_version,
        configured_model=health.configured_model, configured_model_present=health.configured_model_present,
        available_models=health.available_models, loaded_models=health.loaded_models,
        settings=ModelSettingsInForce(
            temperature=settings.model_temperature, seed=settings.model_seed,
            context_window=settings.model_context_window, max_output_tokens=settings.model_max_output_tokens,
        ),
        detail=health.detail,
    )
