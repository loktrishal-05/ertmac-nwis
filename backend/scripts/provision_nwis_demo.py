"""Provision one local demo reviewer; no fixed password, admin, or role override."""
import getpass
import os
from sqlalchemy import select
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db.models import User
from app.db.session import SessionLocal
from app.services.nwis import audit


def provision(session, username, password):
    if settings.deployment_mode != 'development' or session.bind.url.database != 'nwis':
        raise ValueError('Requires development mode and the isolated nwis database')
    if not 1 <= len(username) <= 100 or username.strip() != username:
        raise ValueError('Username must be 1..100 characters without surrounding whitespace')
    if not 16 <= len(password) <= 128:
        raise ValueError('Use a unique demo password of 16..128 characters')
    user = session.scalar(select(User).where(User.username == username))
    if user is not None:
        if (user.role != 'reviewer' or not user.is_active or user.signup_pending
                or not user.password_hash or not verify_password(password, user.password_hash)):
            raise ValueError('Existing account differs; refusing to overwrite credentials or privileges')
        return user
    user = User(username=username, role='reviewer', password_hash=hash_password(password),
                is_active=True, signup_pending=False)
    session.add(user)
    session.flush()
    audit(session, 'demo_reviewer_provisioned', user, role='reviewer')
    session.commit()
    return user


def main():
    username = os.getenv('NWIS_DEMO_USER', 'nwis_demo_reviewer')
    password = os.getenv('NWIS_DEMO_PASSWORD') or getpass.getpass('Unique demo password (16+ characters): ')
    with SessionLocal() as session:
        user = provision(session, username, password)
        print(f'Demo reviewer ready: {user.username}; role={user.role}; terms acceptance required')


if __name__ == '__main__':
    main()
