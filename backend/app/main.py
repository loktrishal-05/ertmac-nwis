"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.router import api_router

app = FastAPI(title="Sovereign On-Premise Agentic AI Workbench")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Phase 5B: the session cookie is HttpOnly and only useful if the browser
    # is allowed to send/receive it. Safe because cors_origins is an explicit
    # whitelist, never "*" (browsers refuse credentials with a wildcard origin).
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


app.include_router(api_router)
