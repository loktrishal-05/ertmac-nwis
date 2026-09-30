"""Create or refresh the public evaluator account shown on the sign-in page.

Idempotent and safe to run on every deployment:  python scripts/seed_demo_account.py
The account is a reviewer (never admin), has no email address (so nobody can take it over through password
recovery), and works only against the synthetic demo dataset. Override with NWIS_DEMO_USERNAME / NWIS_DEMO_PASSWORD;
the frontend reads the same pair from VITE_DEMO_USERNAME / VITE_DEMO_PASSWORD (defaults below match).
"""
import os

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import User
from app.db.models.nwis import Well
from app.db.session import SessionLocal

USERNAME = os.environ.get("NWIS_DEMO_USERNAME", "evaluator")
PASSWORD = os.environ.get("NWIS_DEMO_PASSWORD", "Evaluate-NWIS-2026")
ROLE = os.environ.get("NWIS_DEMO_ROLE", "reviewer")


def main():
    if ROLE not in {"requester", "reviewer"}:
        raise SystemExit("The public demo account may only be a requester or reviewer, never an admin.")
    if len(PASSWORD) < 12:
        raise SystemExit("The demo password must have at least 12 characters.")
    with SessionLocal() as session:
        origins = set(session.scalars(select(Well.dataset_origin)).all())
        if origins != {"synthetic_demo"}:
            raise SystemExit("Public demo access requires an already-seeded, exclusively synthetic NWIS dataset.")
        user = session.scalar(select(User).where(User.username == USERNAME))
        if user is not None and (user.display_name != "Demo Evaluator" or user.email is not None or
                                 user.role not in {"requester", "reviewer"} or user.signup_pending):
            raise SystemExit("Refusing to overwrite an unrelated account with public demo credentials.")
        if user is None:
            user = User(username=USERNAME)
            session.add(user)
        user.display_name = "Demo Evaluator"
        user.role = ROLE
        user.email = None
        user.is_active = True
        user.signup_pending = False
        user.password_hash = hash_password(PASSWORD)
        session.commit()
        print(f"demo account ready: {USERNAME} ({ROLE})", flush=True)


if __name__ == "__main__":
    main()
