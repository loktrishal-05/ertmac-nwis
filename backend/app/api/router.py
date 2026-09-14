"""Collect the foundation routes."""

from fastapi import APIRouter
from app.api.routes import health, query, agents, approvals, documents, audit, sovereignty, knowledge

api_router = APIRouter()
for route_module in (health, query, agents, approvals, documents, audit, sovereignty, knowledge):
    api_router.include_router(route_module.router)
