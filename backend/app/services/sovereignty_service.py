"""Static foundation declaration; no inference or call tracking exists yet."""

from app.schemas.sovereignty import SovereigntyProof


def get_sovereignty_proof() -> SovereigntyProof:
    return SovereigntyProof()
