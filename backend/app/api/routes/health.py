"""Process health, independent of database availability."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.services.readiness import runtime_readiness

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "sovereign-agentic-workbench-backend"}


@router.get('/ready')
def ready():
    result = runtime_readiness()
    return JSONResponse(result, status_code=200 if result['status'] == 'ready' else 503)
