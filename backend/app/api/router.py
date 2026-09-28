"""Collect the foundation routes."""

from fastapi import APIRouter, Depends
from app.api.deps import require_role
from app.api.routes import health, query, agents, approvals, auth, documents, audit, sovereignty, knowledge, pid, maintenance, sensors, models

api_router = APIRouter()
for route_module in (health, query, agents, approvals, auth, documents, audit, sovereignty, knowledge, pid, maintenance, sensors, models):
    dependencies = []
    if route_module in (documents, pid):
        dependencies = [Depends(require_role("admin"))]
    elif route_module in (knowledge, maintenance, sensors):
        dependencies = [Depends(require_role("requester", "reviewer", "admin"))]
    api_router.include_router(route_module.router, dependencies=dependencies)

from app.api.routes import verified_knowledge
api_router.include_router(verified_knowledge.router)

from app.api.routes import knowledge_packs
api_router.include_router(knowledge_packs.router)

from app.api.routes import operational
api_router.include_router(operational.router)

from app.api.routes import product
api_router.include_router(product.router)

from app.api.routes import executions
api_router.include_router(executions.router)
