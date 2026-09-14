"""Process health, independent of database availability."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "sovereign-agentic-workbench-backend"}
