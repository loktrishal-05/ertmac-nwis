"""Only the routes the NWIS frontend calls (WORKBENCH_NWIS_ONLY=1); skips the OCR/vision/agent route stacks."""
from fastapi import APIRouter
from app.api.routes import audit, auth, health, nwis

api_router = APIRouter()
for route_module in (health, auth, audit, nwis):
    api_router.include_router(route_module.router)
