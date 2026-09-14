"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(title="Sovereign On-Premise Agentic AI Workbench")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Report whether the backend process is serving requests."""
    return {
        "status": "ok",
        "service": "sovereign-agentic-workbench-backend",
    }
