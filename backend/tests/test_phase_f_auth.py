"""Deterministic account contracts. Synthetic identities; SMTP and Google never leave the process."""
from contextlib import ExitStack, contextmanager
from datetime import timedelta
import json
import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, settings
from app.core.security import hash_password, hash_session_token, verify_password
from app.db.base import Base
from app.db.models import AuthAttempt, AuthChallenge, AuthIdentity, AuthSession, AuditEvent, OIDCFlow, ResetCapability, User
from app.db.session import get_db
from app.main import app
from app.schemas.auth import CodeRequest
from app.services import accounts as service, auth_delivery, auth_oidc
from app.services.audit import verify_chain
from test_phase5b import TABLES

PASSWORD = "Violet boats carry 57 stones!"
NEW_PASSWORD = "Crimson boats carry 83 pebbles!"
HASH = hash_password(PASSWORD)


class AccountsTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for key, value in {"signup_mode": "approval", "deployment_mode": "development", "auth_secret": "synthetic-test-key-" * 3,
                           "smtp_host": "smtp.local", "smtp_sender": "workbench@example.com", "google_enabled": False,
                           "session_cookie_secure": False, "cors_origins": ["http://testserver", "http://localhost:5173"]}.items():
            self.stack.enter_context(patch.object(settings, key, value))
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        event.listen(self.engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine, tables=TABLES)
        self.addCleanup(self.engine.dispose)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        app.dependency_overrides[get_db] = lambda: self.db
        self.addCleanup(app.dependency_overrides.pop, get_db)
        self.user = User(username="legacy", display_name="Alice Jones", email="alice@example.com", password_hash=HASH,
                         email_verified_at=service.now(), role="requester")
        self.admin = User(username="administrator", display_name="Operator", password_hash=HASH, role="admin")
        self.db.add_all([self.user, self.admin]); self.db.commit()
        self.client = TestClient(app, headers={"Origin": "http://testserver"})
        self.addCleanup(self.client.close)
        self.send = self.stack.enter_context(patch.object(auth_delivery, "send_code"))
        self.stack.enter_context(patch("app.db.session.SessionLocal", side_effect=lambda: Session(self.engine)))

    def post(self, path, **body):
        return self.client.post(path, json=body)

    def login(self, username="legacy", password=PASSWORD):
        response = self.post("/auth/login", username=username, password=password)
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def signup(self, **changes):
        return self.post("/auth/signup", **({"email": "new@example.com", "display_name": "New Person", "password": PASSWORD} | changes))

    def issue(self):
        self.assertEqual(self.post("/auth/password/forgot", email=self.user.email).status_code, 202)
        return self.send.call_args.args[1]

    def verify(self, code):
        return self.post("/auth/password/verify-otp", email=self.user.email, code=code)

    def google(self):
        for key, value in {"google_enabled": True, "google_client_id": "synthetic-client",
                           "google_client_secret": "synthetic-provider-secret", "google_callback_url": "http://localhost:8000/auth/google/callback",
                           "auth_frontend_origin": "http://localhost:5173"}.items():
            self.stack.enter_context(patch.object(settings, key, value))
        self.provider = self.stack.enter_context(patch.object(auth_oidc, "exchange", return_value={
            "sub": "subject-123", "email": self.user.email, "email_verified": True, "name": "Alice Jones"}))

    def flow(self):
        response = self.client.get("/auth/google/start", follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        return parse_qs(urlsplit(response.headers["location"]).query)

    def callback(self, state):
        return self.client.get("/auth/google/callback", params={"code": "synthetic-code", "state": state}, follow_redirects=False)

    def test_signup_approval_and_generic_duplicate(self):
        a = self.signup(email="  NEW@EXAMPLE.COM  ")
        b = self.signup()
        self.assertEqual(a.status_code, 202); self.assertEqual(a.json(), b.json())
        user = self.db.scalar(select(User).where(User.email == "new@example.com"))
        self.assertEqual(user.role, "requester"); self.assertFalse(user.is_active); self.assertTrue(user.signup_pending)
        self.assertTrue(verify_password(PASSWORD, user.password_hash))
        self.assertEqual(self.post("/auth/login", username=user.email, password=PASSWORD).status_code, 401)

    def test_open_signup_and_database_email_constraint(self):
        settings.signup_mode = "open"
        self.signup()
        self.login("NEW@example.com")
        for email in ("new@example.com", "NEW@example.com", " new@example.com "):
            with self.subTest(email=email), self.assertRaises(IntegrityError):
                with self.db.begin_nested():
                    self.db.add(User(username=uuid4().hex, email=email)); self.db.flush()

    def test_signup_rejects_invalid_names_email_password_role_and_mass_assignment(self):
        for change in ({"display_name": "12345"}, {"display_name": "   "}, {"display_name": "hello\nworld"},
                       {"email": "not-email"}, {"email": "a@invalid"}, {"role": "admin"}, {"is_active": True},
                       {"password": "short"}, {"password": "password1234"}, {"password": "NewPerson987654!"}):
            with self.subTest(change=change):
                response = self.signup(**change)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertNotIn(PASSWORD, response.text)

    def test_unicode_name_allowed(self):
        self.assertEqual(self.signup(display_name="தமிழ் 123").status_code, 202)

    def test_disabled_and_confidential_open_refusal(self):
        settings.signup_mode = "disabled"
        self.assertEqual(self.signup().status_code, 403)
        settings.signup_mode, settings.deployment_mode = "open", "confidential"
        self.assertEqual(self.signup().status_code, 403)
        self.assertFalse(self.client.get("/auth/capabilities").json()["signup"])
        with self.assertRaises(ValueError):
            Settings(_env_file=None, model_name="qwen3.5:9b", deployment_mode="confidential", signup_mode="open")

    def test_email_and_legacy_username_login_rotate_session(self):
        self.login()
        old = self.client.cookies.get(settings.session_cookie_name)
        self.login("  ALICE@EXAMPLE.COM  ")
        new = self.client.cookies.get(settings.session_cookie_name)
        self.assertNotEqual(old, new)
        self.assertIsNotNone(self.db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_session_token(old))).revoked_at)
        profile = self.client.get("/auth/me").json()
        self.assertEqual(profile["username"], "legacy"); self.assertEqual(profile["linked_identities"], [])
        self.assertNotIn("password_hash", profile)

    def test_uniform_failures_and_disabled_account_sessions(self):
        responses = [self.post("/auth/login", username="unknown", password=PASSWORD),
                     self.post("/auth/login", username="legacy", password="wrong")]
        self.login(); self.user.is_active = False; self.db.commit()
        responses.append(self.post("/auth/login", username="legacy", password=PASSWORD))
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.assertTrue(all(r.status_code == 401 and r.json() == responses[0].json() for r in responses))

    def test_login_attempts_persist_and_failure_audit_does_not_erase_them(self):
        with patch.object(service, "event", side_effect=RuntimeError("audit down")):
            self.assertEqual(self.post("/auth/login", username="legacy", password="bad").status_code, 401)
        self.assertEqual(self.db.scalar(select(func.max(AuthAttempt.count))), 1)
        for _ in range(9): self.post("/auth/login", username="legacy", password="bad")
        self.assertEqual(self.post("/auth/login", username="legacy", password=PASSWORD).status_code, 401)
        self.assertIsNotNone(self.user.locked_until)

    def test_forgot_known_unknown_cooldown_and_unverified_are_generic(self):
        known = self.post("/auth/password/forgot", email=self.user.email)
        for email in ("nobody@example.com", self.user.email):
            response = self.post("/auth/password/forgot", email=email)
            self.assertEqual((response.status_code, response.json()), (known.status_code, known.json()))
        self.send.assert_called_once()
        self.user.email_verified_at = None; self.db.commit()
        self.post("/auth/password/forgot", email=self.user.email)
        self.send.assert_called_once()

    def test_email_delivery_failure_is_generic_and_code_invalidated(self):
        self.send.side_effect = RuntimeError("do-not-leak-provider-secret")
        response = self.post("/auth/password/forgot", email=self.user.email)
        self.assertEqual(response.status_code, 202)
        self.assertNotIn("do-not-leak", response.text)
        self.db.expire_all()
        self.assertIsNotNone(self.db.scalar(select(AuthChallenge)).consumed_at)

    def test_otp_hash_attempt_exhaustion(self):
        code = self.issue()
        challenge = self.db.scalar(select(AuthChallenge))
        self.assertNotEqual(code, challenge.code_hash)
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5): self.assertEqual(self.verify(wrong).status_code, 400)
        self.assertEqual(self.verify(code).status_code, 400)
        self.assertEqual(challenge.attempts, 5)

    def test_otp_expiry(self):
        code = self.issue()
        self.db.scalar(select(AuthChallenge)).expires_at = service.now() - timedelta(seconds=1); self.db.commit()
        self.assertEqual(self.verify(code).status_code, 400)

    def test_reset_revokes_all_sessions_and_replays_fail(self):
        self.login(); old = self.client.cookies.get(settings.session_cookie_name)
        self.client.cookies.clear(); self.login()
        code = self.issue(); verified = self.verify(code)
        self.assertEqual(verified.status_code, 200, verified.text)
        token = verified.json()["reset_token"]
        self.assertEqual(self.verify(code).status_code, 400)
        grant = self.db.scalar(select(ResetCapability)); self.assertNotEqual(token, grant.token_hash)
        response = self.post("/auth/password/reset", reset_token=token, new_password=NEW_PASSWORD)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.post("/auth/password/reset", reset_token=token, new_password=PASSWORD).status_code, 400)
        self.client.cookies.set(settings.session_cookie_name, old)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.revoked_at.is_(None))), 0)
        self.login(password=NEW_PASSWORD)

    def test_reset_expiry_and_invalid_token(self):
        token = self.verify(self.issue()).json()["reset_token"]
        self.db.scalar(select(ResetCapability)).expires_at = service.now() - timedelta(seconds=1); self.db.commit()
        for value in (token, "x" * 43):
            self.assertEqual(self.post("/auth/password/reset", reset_token=value, new_password=NEW_PASSWORD).status_code, 400)

    def test_request_rate_limit_does_not_reveal_account(self):
        for _ in range(5):
            self.assertEqual(self.post("/auth/password/forgot", email=self.user.email).json(), service.GENERIC)
        self.send.assert_called_once()

    def test_resend_invalidates_previous_code(self):
        code = self.issue()
        self.db.scalar(select(AuthChallenge)).created_at = service.now() - timedelta(seconds=61); self.db.commit()
        with patch.object(service.secrets, "randbelow", return_value=(int(code) + 1) % 1000000):
            newer = self.issue()
        self.assertEqual(self.verify(code).status_code, 400)
        self.assertEqual(self.verify(newer).status_code, 200)

    def test_email_verification_separate_from_activation_and_password(self):
        self.user.email_verified_at, self.user.is_active, self.user.signup_pending = None, False, True; self.db.commit()
        self.post("/auth/email/request-verification", email=self.user.email)
        code = self.send.call_args.args[1]
        self.assertEqual(self.verify(code).status_code, 400)
        self.assertEqual(self.post("/auth/email/verify", email=self.user.email, code=code).status_code, 200)
        self.assertIsNotNone(self.user.email_verified_at); self.assertFalse(self.user.is_active)

    def test_offline_admin_recovery_of_legacy_user(self):
        settings.smtp_host = ""
        self.user.email, self.user.email_verified_at = None, None; self.db.commit()
        self.login("administrator")
        response = self.post(f"/admin/users/{self.user.id}/recovery")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.post(f"/admin/users/{self.user.id}/recovery").status_code, 429)
        self.client.cookies.clear()
        verified = self.post("/auth/password/verify-otp", username="legacy", code=response.json()["code"])
        self.assertEqual(verified.status_code, 200)
        self.post("/auth/password/reset", reset_token=verified.json()["reset_token"], new_password=NEW_PASSWORD)
        self.login(password=NEW_PASSWORD)
        self.send.assert_not_called(); self.assertIsNone(self.user.email_verified_at)

    def test_disabled_account_recovery_does_not_reactivate(self):
        self.login("administrator")
        self.user.is_active = False; self.db.commit()
        code = self.post(f"/admin/users/{self.user.id}/recovery").json()["code"]
        token = self.verify(code).json()["reset_token"]
        self.post("/auth/password/reset", reset_token=token, new_password=NEW_PASSWORD)
        self.assertFalse(self.user.is_active)

    def test_capabilities_safe_and_offline_without_secret(self):
        data = self.client.get("/auth/capabilities").json()
        self.assertTrue(data["local_login"] and data["admin_recovery"])
        self.assertNotIn(settings.auth_secret, json.dumps(data))
        settings.auth_secret = ""
        data = self.client.get("/auth/capabilities").json()
        self.assertFalse(data["email_recovery"] or data["admin_recovery"] or data["google"])
        self.assertEqual(data["email_delivery"], "none")
        self.login()

    def test_capabilities_report_where_codes_are_delivered(self):
        self.assertEqual(self.client.get("/auth/capabilities").json()["email_delivery"], "smtp")
        with patch.object(settings, "smtp_host", "localhost"):
            self.assertEqual(self.client.get("/auth/capabilities").json()["email_delivery"], "local")

    def test_admin_authorization_role_change_and_revocation(self):
        self.assertEqual(self.client.get("/admin/users").status_code, 401)
        self.login(); cookie = self.client.cookies.get(settings.session_cookie_name)
        self.assertEqual(self.client.get("/admin/users").status_code, 403)
        self.assertEqual(self.post(f"/admin/users/{self.user.id}/role", role="admin").status_code, 403)
        self.login("administrator")
        self.assertEqual(self.post(f"/admin/users/{self.user.id}/role", role="reviewer").status_code, 200)
        self.client.cookies.clear(); self.client.cookies.set(settings.session_cookie_name, cookie)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.assertEqual(self.user.role, "reviewer")

    def test_admin_approval_deactivation_and_no_self_escalation(self):
        self.signup(); self.login("administrator")
        pending = self.db.scalar(select(User).where(User.email == "new@example.com"))
        self.assertEqual(self.post(f"/admin/users/{pending.id}/activate").status_code, 409)
        self.assertEqual(self.post(f"/admin/users/{pending.id}/approve").status_code, 200)
        self.assertTrue(pending.is_active); self.assertFalse(pending.signup_pending)
        self.assertEqual(self.post(f"/admin/users/{self.admin.id}/role", role="requester").status_code, 409)
        self.assertEqual(self.post(f"/admin/users/{self.admin.id}/deactivate").status_code, 409)
        self.assertEqual(self.post(f"/admin/users/{pending.id}/deactivate").status_code, 200)
        self.assertFalse(pending.is_active)

    def test_admin_create_and_mass_assignment(self):
        self.login("administrator")
        body = dict(display_name="Offline Person", username="offline", password=PASSWORD, role="reviewer")
        self.assertEqual(self.post("/admin/users", **body, is_active=True).status_code, 422)
        response = self.post("/admin/users", **body)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertIsNone(response.json()["email"])
        self.assertEqual(self.post("/admin/users", **body).status_code, 409)

    def test_session_ownership_and_revoke_all(self):
        self.login(); own = self.client.get("/auth/sessions").json()[0]
        self.assertTrue(own["current"]); self.assertNotIn("token_hash", own)
        self.client.cookies.clear(); self.login("administrator")
        self.assertEqual(self.post(f"/auth/sessions/{own['id']}/revoke").status_code, 404)
        self.assertEqual(self.post("/auth/sessions/revoke-all").status_code, 200)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)

    def test_csrf_origins_and_validation_never_echo_secrets(self):
        for origin in ("https://evil.example", "null"):
            response = self.client.post("/auth/login", headers={"Origin": origin}, json={"username": "legacy", "password": PASSWORD})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post("/auth/login", data={"username": "legacy", "password": PASSWORD}).status_code, 422)
        response = self.post("/auth/signup", email="bad", display_name="123", password="short-secret")
        self.assertNotIn("short-secret", response.text)
        no_origin = TestClient(app, headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(no_origin.post("/auth/logout").status_code, 403)
        self.assertEqual(no_origin.get("/approvals/anything/release").status_code, 403)

    def test_audit_integrity_and_no_secrets(self):
        self.login(); code = self.issue(); token = self.verify(code).json()["reset_token"]
        self.post("/auth/password/reset", reset_token=token, new_password=NEW_PASSWORD)
        self.assertTrue(verify_chain(self.db)["valid"])
        payloads = json.dumps([event.payload for event in self.db.scalars(select(AuditEvent))], default=str)
        for value in (PASSWORD, NEW_PASSWORD, code, token, settings.auth_secret):
            self.assertNotIn(value, payloads)

    def test_google_pkce_state_binding_and_replay(self):
        self.google(); query = self.flow()
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertIn("nonce", query); self.assertNotIn("code_verifier", query)
        state = query["state"][0]
        row = self.db.scalar(select(OIDCFlow)); self.assertNotEqual(row.state_hash, state)
        self.assertIn("status=failed", self.callback("wrong-state").headers["location"])
        self.provider.assert_not_called()
        # Invalid callback clears the cookie, requiring a fresh flow.
        state = self.flow()["state"][0]
        self.assertIn("status=success", self.callback(state).headers["location"])
        self.assertIn("status=failed", self.callback(state).headers["location"])
        self.provider.assert_called_once()

    def test_google_expired_or_unbound_flow(self):
        self.google(); state = self.flow()["state"][0]
        self.db.scalar(select(OIDCFlow)).expires_at = service.now() - timedelta(seconds=1); self.db.commit()
        self.assertIn("failed", self.callback(state).headers["location"])
        state = self.flow()["state"][0]; self.client.cookies.clear()
        self.assertIn("failed", self.callback(state).headers["location"])
        self.provider.assert_not_called()

    def test_google_existing_verified_account_links_once(self):
        self.google()
        for _ in range(2):
            self.assertIn("success", self.callback(self.flow()["state"][0]).headers["location"])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(User)), 2)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(AuthIdentity)), 1)
        self.assertEqual(self.client.get("/auth/me").json()["linked_identities"], ["google"])

    def test_google_unverified_local_email_is_not_linked(self):
        self.google(); self.user.email_verified_at = None; self.db.commit()
        self.assertIn("failed", self.callback(self.flow()["state"][0]).headers["location"])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(AuthIdentity)), 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(User)), 2)

    def test_provider_only_account_cannot_use_dummy_password(self):
        self.user.password_hash = None; self.db.commit()
        response = self.post("/auth/login", username="legacy", password="dummy-account-verification-not-a-login-password")
        self.assertEqual(response.status_code, 401)

    def test_email_login_normalizes_international_domain(self):
        self.user.email = "alice@bücher.de"; self.db.commit()
        self.login(" ALICE@xn--bcher-kva.de ")

    def test_google_malformed_email_fails_without_provider_details(self):
        self.google(); self.provider.return_value["email"] = "invalid"
        self.assertIn("status=failed", self.callback(self.flow()["state"][0]).headers["location"])

    def test_callback_scope_is_redacted_before_access_logging(self):
        seen = []
        async def wrapped(scope, receive, send):
            async def capture(message):
                if message["type"] == "http.response.start":
                    seen.append(scope["query_string"])
                await send(message)
            await app(scope, receive, capture)
        with TestClient(wrapped) as client:
            client.get("/auth/google/callback?code=secret-code&state=secret-state")
            client.get("/auth/google/callback?code=" + "x" * 5000)
        self.assertEqual(seen, [b"", b""])

    def test_google_new_account_obeys_signup_policy(self):
        self.google(); self.provider.return_value = {"sub": "new-subject", "email": "another@example.com", "email_verified": True}
        self.assertIn("pending_or_inactive", self.callback(self.flow()["state"][0]).headers["location"])
        new = self.db.scalar(select(User).where(User.email == "another@example.com"))
        self.assertEqual(new.role, "requester"); self.assertTrue(new.signup_pending); self.assertIsNone(new.password_hash)
        settings.signup_mode = "disabled"
        self.provider.return_value = {"sub": "disabled-subject", "email": "third@example.com", "email_verified": True}
        self.assertIn("failed", self.callback(self.flow()["state"][0]).headers["location"])

    def test_google_open_and_changed_provider_email_uses_subject(self):
        self.google(); settings.signup_mode = "open"
        self.provider.return_value = {"sub": "new-subject", "email": "another@example.com", "email_verified": True}
        self.assertIn("success", self.callback(self.flow()["state"][0]).headers["location"])
        identifier = self.client.get("/auth/me").json()["id"]
        self.provider.return_value["email"] = "changed@example.com"
        self.assertIn("success", self.callback(self.flow()["state"][0]).headers["location"])
        self.assertEqual(self.client.get("/auth/me").json()["id"], identifier)

    def test_google_disabled_confidential_and_provider_failure_consumes_state(self):
        self.google(); settings.deployment_mode = "confidential"
        self.assertFalse(self.client.get("/auth/capabilities").json()["google"])
        self.assertEqual(self.client.get("/auth/google/start").status_code, 404)
        self.assertEqual(self.callback("anything").status_code, 404)
        self.provider.assert_not_called()
        settings.deployment_mode = "development"
        state = self.flow()["state"][0]; self.provider.side_effect = RuntimeError("private-provider-secret")
        result = self.callback(state)
        self.assertNotIn("private-provider-secret", result.text)
        self.assertIsNotNone(self.db.scalar(select(OIDCFlow)).consumed_at)


class GoogleTokenTests(unittest.TestCase):
    def test_real_signature_claims_nonce_and_bounded_exchange(self):
        from authlib.jose import JsonWebKey, jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        jwk = JsonWebKey.import_key(pem, {"kid": "test"})
        with patch.object(settings, "auth_secret", "synthetic-key" * 4), patch.object(settings, "google_client_id", "client"):
            claims = {"iss": "https://accounts.google.com", "sub": "123", "aud": "client", "email": "a@example.com",
                      "email_verified": True, "exp": int(service.now().timestamp()) + 300,
                      "iat": int(service.now().timestamp()), "nonce": auth_oidc.derived("oidc-nonce", "state")}
            @contextmanager
            def response(data):
                yield httpx.Response(200, json=data, request=httpx.Request("POST", "https://example.com"))
            for change in ({}, {"nonce": "wrong"}, {"iss": "https://evil.example"}, {"aud": "other"},
                           {"email_verified": False}, {"exp": 1}, {"azp": "other"}):
                token = jwt.encode({"alg": "RS256", "kid": "test"}, claims | change, jwk).decode()
                oauth, http = MagicMock(), MagicMock()
                oauth.__enter__.return_value = oauth; http.__enter__.return_value = http
                oauth.stream.side_effect = lambda *a, **kw: response({"id_token": token})
                http.stream.side_effect = lambda *a, **kw: response({"keys": [jwk.as_dict(is_private=False)]})
                with self.subTest(change=change), patch.object(auth_oidc, "oauth_client", return_value=oauth), \
                        patch.object(auth_oidc.httpx, "Client", return_value=http):
                    if change:
                        with self.assertRaises(Exception): auth_oidc.exchange("code", "state")
                    else:
                        self.assertEqual(auth_oidc.exchange("code", "state")["sub"], "123")
                    self.assertEqual(oauth.stream.call_args.kwargs["data"]["code_verifier"], auth_oidc.derived("oidc-pkce", "state"))

    def test_confidential_smtp_rejects_public_resolution_before_connection(self):
        with patch.object(settings, "deployment_mode", "confidential"), patch.object(settings, "smtp_host", "smtp.local"), \
                patch.object(auth_delivery.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("8.8.8.8", 587))]), \
                patch.object(auth_delivery.socket, "create_connection") as connect:
            with self.assertRaises(ValueError): auth_delivery.send_code("a@example.com", "123456", "password")
            connect.assert_not_called()
