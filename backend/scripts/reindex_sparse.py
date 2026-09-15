"""Explicit idempotent in-place sparse backfill. No collection recreation."""
import json
import argparse
from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.qdrant_service import get_qdrant


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--promote", action="store_true", help="After copy verification, replace the original physical collection with an alias; retain full dense backup")
    args = parser.parse_args()
    with SessionLocal() as session:
        if not session.scalar(text("SELECT pg_try_advisory_xact_lock(3302001)")):
            raise RuntimeError("Ingestion is active; retry migration during a maintenance window")
        print(json.dumps(get_qdrant().migrate_sparse(promote=args.promote), indent=2))
