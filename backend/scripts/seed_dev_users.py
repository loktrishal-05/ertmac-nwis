"""Create/update two local-development-only Phase 5B test users: a requester
and a reviewer, with known passwords, for exercising the real authenticated
approval flow. Never run against a shared or production database."""
from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import User
from app.db.session import SessionLocal

DEV_USERS = [
    ("dev_requester", "dev-requester-pass-1", "requester"),
    ("dev_reviewer", "dev-reviewer-pass-1", "reviewer"),
]


def main():
    with SessionLocal() as session:
        for username, password, role in DEV_USERS:
            user = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
            if user is None:
                user = User(username=username, role=role)
                session.add(user)
            user.role = role
            user.password_hash = hash_password(password)
            session.flush()
            print(username, user.id, role, flush=True)
        session.commit()


if __name__ == "__main__":
    main()
