"""Collect the foundation routes."""

from fastapi import APIRouter
from app.api.routes import health, query, agents, approvals, auth, documents, audit, sovereignty, knowledge, pid, maintenance, sensors, models

api_router = APIRouter()
for route_module in (health, query, agents, approvals, auth, documents, audit, sovereignty, knowledge, pid, maintenance, sensors, models):
    api_router.include_router(route_module.router)

from app.api.routes import verified_knowledge
api_router.include_router(verified_knowledge.router)
