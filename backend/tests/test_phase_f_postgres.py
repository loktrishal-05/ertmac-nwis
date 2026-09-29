"""Real PostgreSQL migration and competing account transactions in a disposable schema."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import os
from pathlib import Path
from threading import Barrier
import unittest
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_session_token, verify_password
from app.db.models import AuthAttempt, AuthIdentity, AuthSession, ResetCapability, User
from app.schemas.auth import CodeRequest, SignupRequest
from app.services import accounts, auth_oidc
from app.services.audit import verify_chain
from test_phase_f_auth import HASH, PASSWORD, NEW_PASSWORD


@unittest.skipUnless(os.environ.get("WORKBENCH_TEST_POSTGRES") == "1", "Real PostgreSQL integration not enabled")
class PostgreSQLAccountsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_phase_f_" + uuid4().hex
        cls.admin = create_engine(settings.database_url)
        with cls.admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.addClassCleanup(cls.cleanup)
        url = make_url(settings.database_url).update_query_dict({"options": f"-csearch_path={cls.schema}"})
        cls.url = url.render_as_string(hide_password=False)
        cls.engine = create_engine(url)
        cls.addClassCleanup(cls.engine.dispose)
        cls.config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with patch.object(settings, "database_url", cls.url):
            command.upgrade(cls.config, "0016_enterprise_knowledge")
            cls.legacy_id = uuid4()
            with cls.engine.begin() as conn:
                conn.execute(text("INSERT INTO users (id, username, role, password_hash) VALUES (:id, 'preserved', 'requester', :hash)"),
                             {"id": cls.legacy_id, "hash": HASH})
            command.upgrade(cls.config, "head")
            command.check(cls.config)

    @classmethod
    def cleanup(cls):
        assert cls.schema.startswith("test_phase_f_") and len(cls.schema) == 45
        with cls.admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))
        cls.admin.dispose()

    def setUp(self):
        stack = ExitStack(); self.addCleanup(stack.close)
        for key, value in {"auth_secret": "postgres-synthetic-key-" * 3, "signup_mode": "open", "deployment_mode": "development",
                           "google_enabled": True, "google_client_id": "synthetic", "google_client_secret": "synthetic",
                           "google_callback_url": "http://localhost:8000/auth/google/callback",
                           "auth_frontend_origin": "http://localhost:5173", "cors_origins": ["http://localhost:5173"]}.items():
            stack.enter_context(patch.object(settings, key, value))

    def user(self, **values):
        with Session(self.engine) as db:
            user = User(username="u_" + uuid4().hex, display_name="Test Person", password_hash=HASH, **values)
            db.add(user); db.commit()
            return user.id

    def race(self, action, count=2):
        barrier = Barrier(count)
        def worker(index):
            with Session(self.engine) as db:
                barrier.wait(timeout=10)
                try:
                    result = action(db, index)
                    db.commit()
                    return result
                except HTTPException as exc:
                    db.rollback()
                    return exc.status_code
        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(worker, i) for i in range(count)]
            return [future.result(timeout=30) for future in futures]

    def test_migration_preserves_legacy_and_constraints(self):
        with Session(self.engine) as db:
            user = db.get(User, self.legacy_id)
            self.assertEqual(user.display_name, "preserved")
            self.assertIsNone(user.email); self.assertTrue(user.is_active); self.assertFalse(user.signup_pending)
            self.assertTrue(verify_password(PASSWORD, user.password_hash))
            self.assertEqual(db.scalar(text("SELECT version_num FROM alembic_version")), "0017_accounts_recovery")
            accounts.login(db, "preserved", PASSWORD, str(uuid4()))
        with self.assertRaises(DBAPIError), self.engine.begin() as conn:
            conn.execute(text("UPDATE users SET email='UPPER@example.com' WHERE id=:id"), {"id": self.legacy_id})
        with patch.object(settings, "database_url", self.url), self.assertRaises(DBAPIError):
            command.downgrade(self.config, "0016_enterprise_knowledge")

    def test_competing_signup_creates_one_requester(self):
        email = uuid4().hex + "@example.com"
        payload = SignupRequest(email=email, display_name="Concurrent Person", password=PASSWORD)
        self.race(lambda db, i: accounts.signup(db, payload, str(uuid4())))
        with Session(self.engine) as db:
            users = db.scalars(select(User).where(User.email == email)).all()
            self.assertEqual(len(users), 1); self.assertEqual(users[0].role, "requester")

    def test_database_counter_is_atomic(self):
        key = str(uuid4())
        values = self.race(lambda db, i: accounts.budget(db, "race", key, 2), count=4)
        self.assertEqual(values.count(True), 2)
        with Session(self.engine) as db:
            self.assertEqual(db.get(AuthAttempt, hash_session_token("race:" + key)).count, 4)

    def test_one_otp_redemption_and_one_reset_win(self):
        user_id = self.user()
        with Session(self.engine) as db:
            user = db.get(User, user_id)
            _, code = accounts.issue_code(db, user, "password", actor=user)
            username = user.username
            accounts.issue_session(db, user); db.commit()
        values = self.race(lambda db, i: accounts.verify_code(db, CodeRequest(username=username, code=code), str(uuid4()), "password"))
        self.assertEqual(values.count(400), 1)
        token = next(v["reset_token"] for v in values if isinstance(v, dict))
        resets = self.race(lambda db, i: accounts.reset_password(db, token, NEW_PASSWORD, str(uuid4())))
        self.assertEqual(resets.count(400), 1); self.assertEqual(resets.count(None), 1)
        with Session(self.engine) as db:
            self.assertTrue(verify_password(NEW_PASSWORD, db.get(User, user_id).password_hash))
            self.assertEqual(db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))), 0)

    def test_reset_failure_rolls_back_password_token_and_revocation(self):
        user_id = self.user()
        token = "synthetic-reset-token-" + uuid4().hex
        with Session(self.engine) as db:
            user = db.get(User, user_id)
            accounts.issue_session(db, user)
            from datetime import timedelta
            db.add(ResetCapability(user_id=user_id, token_hash=hash_session_token(token), expires_at=accounts.now() + timedelta(minutes=10)))
            db.commit()
        with Session(self.engine) as db, patch.object(accounts, "event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError): accounts.reset_password(db, token, NEW_PASSWORD, str(uuid4()))
            db.rollback()
        with Session(self.engine) as db:
            self.assertTrue(verify_password(PASSWORD, db.get(User, user_id).password_hash))
            self.assertIsNone(db.scalar(select(ResetCapability).where(ResetCapability.user_id == user_id)).consumed_at)
            self.assertEqual(db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))), 1)

    def test_competing_admin_demotions_preserve_one_admin(self):
        ids = [self.user(role="admin"), self.user(role="admin")]
        values = self.race(lambda db, i: accounts.administer(db, ids[i], ids[1-i], "role", "requester"))
        self.assertEqual(values.count(403), 1)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(User).where(User.id.in_(ids), User.role == "admin")), 1)
            self.assertTrue(verify_chain(db)["valid"])

    def test_google_state_redeems_once(self):
        with Session(self.engine) as db:
            url, binding = auth_oidc.start(db, str(uuid4()))
        from urllib.parse import urlsplit, parse_qs
        state = parse_qs(urlsplit(url).query)["state"][0]
        values = self.race(lambda db, i: auth_oidc.consume_flow(db, state, binding, str(uuid4())))
        self.assertEqual(values.count(None), 1); self.assertEqual(values.count(400), 1)

    def test_competing_google_links_do_not_duplicate_email(self):
        email = uuid4().hex + "@example.com"
        claims = {"sub": uuid4().hex, "email": email, "email_verified": True}
        def action(db, index):
            from urllib.parse import urlsplit, parse_qs
            url, binding = auth_oidc.start(db, str(uuid4()))
            return auth_oidc.callback(db, "mock", parse_qs(urlsplit(url).query)["state"][0], binding, str(uuid4()))[1]
        with patch.object(auth_oidc, "exchange", return_value=claims):
            self.assertEqual(self.race(action), ["success", "success"])
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(User).where(User.email == email)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(AuthIdentity).where(AuthIdentity.subject == claims["sub"])), 1)
            self.assertTrue(verify_chain(db)["valid"])
