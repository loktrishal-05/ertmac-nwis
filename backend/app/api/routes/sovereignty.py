"""Sovereignty declaration endpoint."""

from fastapi import APIRouter
from app.schemas.sovereignty import SovereigntyProof
from app.services.sovereignty_service import get_sovereignty_proof

router = APIRouter(tags=["sovereignty"])


@router.get("/sovereignty/proof", response_model=SovereigntyProof)
def sovereignty_proof() -> SovereigntyProof:
    return get_sovereignty_proof()
