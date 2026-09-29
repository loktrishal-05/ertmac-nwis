# Phase F authentication backend

Supported runtime: the existing Linux Docker backend, Python 3.11 and the CPU
dependency lock. Migration `0017_accounts_recovery` follows `0016_enterprise_knowledge`.
Legacy usernames, password hashes, roles and sessions are preserved. Existing users
remain active; email is nullable. The migration backfills display names from usernames.
Email writes must be lowercase/trimmed; a PostgreSQL unique index on `lower(email)`
prevents concurrent duplicate accounts. Downgrade refuses when account history would
be lost. Use the existing backup and migration-owner procedure before upgrading.

## Configuration

The existing Compose overlay reads protected root `.env`. No real credentials are
needed by the tests. Never commit that file or print its values.

| Setting | Meaning/default |
| --- | --- |
| `WORKBENCH_SIGNUP_MODE` | `approval` (default), `disabled`, or `open` |
| `WORKBENCH_AUTH_SECRET` | Protected random secret, at least 32 bytes; required for recovery and OIDC |
| `SESSION_COOKIE_SECURE` | Set `true` behind HTTPS; local HTTP development uses `false` |
| `WORKBENCH_CORS_ORIGINS` | JSON array of exact trusted browser origins |
| `WORKBENCH_SMTP_HOST`, `WORKBENCH_SMTP_PORT` | Optional relay; default port 587 |
| `WORKBENCH_SMTP_SENDER` | Relay-approved sender address |
| `WORKBENCH_SMTP_USERNAME`, `WORKBENCH_SMTP_PASSWORD` | Optional relay credentials |
| `WORKBENCH_SMTP_TLS` | `starttls` (default) or `tls`; `none` only on development loopback |
| `WORKBENCH_GOOGLE_ENABLED` | `false` by default |
| `WORKBENCH_GOOGLE_CLIENT_ID`, `WORKBENCH_GOOGLE_CLIENT_SECRET` | Optional server OAuth client registration |
| `WORKBENCH_GOOGLE_CALLBACK_URL` | Exact registered backend URL ending `/auth/google/callback` |
| `WORKBENCH_AUTH_FRONTEND_ORIGIN` | Trusted frontend origin, also present in CORS origins |

Generate the authentication secret locally with an approved secret manager or
`python -c "import secrets; print(secrets.token_urlsafe(48))"` and store it securely.
All backend workers must share it. Rotating it invalidates pending OTPs and OIDC
flows; already issued reset capabilities retain their short expiry. With an empty
secret, local login and administration still work; recovery/OIDC capabilities are
disabled. Keep secrets out of shell history, diagnostics and support bundles.

Confidential deployments reject open signup at configuration validation and at the
signup boundary. Google is always disabled in confidential mode. SMTP must be a
private/on-premise relay: configuration and every resolved destination are checked,
and the connection is pinned to the checked address. TLS verifies the relay hostname.
For fully offline operation, leave SMTP/Google unconfigured, set the local authentication
secret, and use administrator recovery. Neither service enters inference or is a
fallback for confidential processing. Existing loopback-only published ports remain.

Connected/public Google deployments require HTTPS and secure session cookies.
Development permits HTTP only for loopback URLs. Register the backend callback with
Google, not the frontend callback. The server uses authorization code, S256 PKCE,
one-use state, a browser binding cookie, and a validated nonce/issuer/audience/signature.
It does not store provider access/refresh tokens. The frontend receives only a redirect
to `/auth/callback?status=success|pending_or_inactive|failed`, plus an HttpOnly session
cookie on success. Tokens never appear in that redirect. Backend callback query strings
are removed before Uvicorn access logging; configure any upstream proxy to omit query
strings and request/response bodies for authentication routes too.

## HTTP contract

All state changes are POST. Browser clients must use an allowed Origin and
`credentials: "include"`. Cross-origin/null-origin requests are rejected; Referer and
Fetch Metadata cover requests without Origin. Headerless nonbrowser clients retain
the existing API behavior. Authentication/admin responses are `no-store` and
`no-referrer`; validation errors omit submitted values. Do not log sensitive bodies.

| Endpoint | Body/result |
| --- | --- |
| `GET /auth/capabilities` | Booleans `local_login`, `signup`, `password_recovery`, `email_recovery`, `admin_recovery`, `google`; `signup_mode` |
| `POST /auth/signup` | `display_name`, `email`, `password`; generic 202 |
| `POST /auth/login` | `username` (legacy username **or email**), `password`; public user and rotated session cookie |
| `POST /auth/logout` | Revoke current session; clear cookie |
| `GET /auth/me` | Current public account and `linked_identities` provider names |
| `GET /auth/sessions` | Up to 100 active sessions: ID, creation/expiry, current flag; no tokens |
| `POST /auth/sessions/{id}/revoke` | Revoke an owned session |
| `POST /auth/sessions/revoke-all` | Revoke all owned sessions, including current |
| `POST /auth/email/request-verification` | `email`; generic 202 |
| `POST /auth/email/verify` | `email`, `code`; mark email verified, without activating pending signup |
| `POST /auth/password/forgot` | `email`; identical 202 for known/unknown/ineligible/rate-limited addresses |
| `POST /auth/password/verify-otp` | Exactly one of `email`/`username`, plus `code`; one-use `reset_token`, `expires_in` |
| `POST /auth/password/reset` | `reset_token`, `new_password`; consumes grants/codes and revokes all sessions |
| `GET /auth/google/start` | Redirect to Google; sets temporary HttpOnly binding cookie |
| `GET /auth/google/callback` | Server callback; browser redirect described above |
| `GET /admin/users` | Admin only; `offset`, `limit` (max 100), optional `pending` |
| `POST /admin/users` | Admin only; `display_name`, `password`, `role`, and `email` and/or `username` |
| `POST /admin/users/{id}/approve` | Approve a pending signup |
| `POST /admin/users/{id}/activate` | Reactivate a nonpending user |
| `POST /admin/users/{id}/deactivate` | Deactivate and revoke sessions |
| `POST /admin/users/{id}/role` | `role`: requester/reviewer/admin; revoke sessions |
| `POST /admin/users/{id}/revoke-sessions` | Revoke target sessions |
| `POST /admin/users/{id}/recovery` | Return temporary code once, username/email and 600-second expiry |

Signup never accepts a role or activation flags; new users are requesters. Approval
mode creates inactive pending users. Names need at least one letter. Email syntax
is validated without network lookups. Passwords need 12–128 characters and cannot
contain name/email components or the small built-in common-password denylist; this
is not a comprehensive breached-password database. Legacy passwords remain valid.

Email verification is a separate request after signup; signup does not imply a sent
email. Forgot-password sends only to a verified, active account. Six-digit codes
expire after ten minutes, allow five wrong attempts and have a 60-second resend
cooldown. Only an HMAC is stored. Verification consumes the code and issues a random
ten-minute reset capability stored as a hash. Resends invalidate older codes and
outstanding reset capabilities. Reset does not reactivate a disabled account.
SMTP runs after commit, with no persisted plaintext outbox; delivery failure
invalidates the challenge when the database is reachable and records a safe event.
Responses remain generic. The user can retry after the cooldown.

Rate state is database-backed across workers. Login allows 30 attempts/IP and ten
attempts/identifier per 15 minutes; ten wrong account passwords lock it for 15 minutes.
Signup allows five/IP/hour. Email requests allow 20/IP and three/address per 15
minutes, verification 20/IP and ten/identifier, reset 20/IP. Do not trust arbitrary
forwarded-IP headers; configure the existing proxy trust boundary explicitly.

For offline recovery an authenticated admin issues a code, conveys it through an
approved local channel, and the user redeems it with their legacy username. Issuance
is audited and rate-limited. Code retrieval is one-time; no email is necessary.
Admins cannot change their own role or deactivate themselves. PostgreSQL serializes
membership changes and rechecks actor authorization, preventing competing changes
from eliminating the final active admin. All privileged mutations append to the
existing tamper-evident audit chain within the same transaction.

Google linking first uses the provider subject. A new subject may link only to a
verified local email with no conflicting Google identity. An unverified local email
must be verified through local authentication first. New Google accounts follow
signup policy and are requesters. Unique identity/email constraints and conflict
rechecks prevent duplicate-account races. Google-only accounts cannot log in using
the dummy password used to equalize unknown-account password verification cost.

## Validation

Use the existing Linux image and an explicitly disposable PostgreSQL database:

```sh
python -m alembic -c backend/alembic.ini upgrade head
python -m alembic -c backend/alembic.ini check
WORKBENCH_TEST_POSTGRES=1 python -m unittest discover -s backend/tests -p 'test_phase_f*.py' -v
WORKBENCH_TEST_POSTGRES=1 python -m unittest discover -s backend/tests -v
python -m scripts.frozen_integrity
```

Tests mock SMTP and Google. They use synthetic secrets, real signed test ID tokens,
and isolated PostgreSQL schemas for migration/atomicity/concurrency checks. Do not
run this suite against production data. On this Windows development host, copy the
worktree to a disposable Linux checkout for the full suite; Windows bind-mount import
latency can exceed the existing live-server test's startup budget. The image locks
Authlib/email-validator and their added transitive dependencies without changing
baseline package versions. Include those wheels in the approved offline bundle,
or transfer the rebuilt signed image as described in the deployment guide.

No frontend source is changed here. H3 identifier review remains the first required
Phase F frontend item. BLIND is not part of these commands and must not be executed.

### Validated on 2026-09-29

- Frozen baseline: `2f52117`; isolated branch `feat/phase-f-auth`.
- Rebuilt the existing `infra/Dockerfile.backend` as `sovereign-phase-f-auth:release`;
  image ID `sha256:70511e6c5798b1e49087dd45bf207575f5df223adaeb80b5c6f4e4915bde3e0f`.
  Python 3.11.16, all 182 locked packages verified, Torch 2.14.0+cpu, CUDA absent,
  and `pip check` passed. The lock adds four packages; existing pins are unchanged.
- Targeted authentication/concurrency and legacy migration regressions: 49 passed.
- Full final image run with disposable PostgreSQL 17: **937 passed, 0 failed,
  0 errors, 1 skipped** (the existing opt-in live-model query), 938 tests total.
  This includes Phase 11/security, Phase D/D-LIVE, Phase E and existing approval/RBAC tests.
- Upgrade from populated 0016 preserves legacy login; head is 0017. Alembic metadata
  checks, safe downgrade/upgrade and refusal of lossy downgrade passed.
- Frozen benchmark: **168/168 PASS**, with evaluation-asset guards also passing.
  BLIND was not executed. SMTP/Google tests used only synthetic credentials and mocks.
- The first full attempt exposed Windows archive line-ending conversion, build-time
  contention during server startup, and an overly strict null-display-name downgrade
  guard. Validation now clones a Git bundle into Linux, runs after the image build,
  and the guard permits legacy null names while refusing loss of account history.
  Existing test fixture table lists/counts were updated for the five new tables.
- Main worktree/frontend, Windows security settings and existing application/database
  containers were unchanged. No production migration, push or merge was performed.

### Files changed

```text
.env.example
backend/alembic/versions/0017_accounts_recovery.py
backend/app/api/deps.py
backend/app/api/routes/auth.py
backend/app/core/config.py
backend/app/db/models/__init__.py
backend/app/db/models/account_auth.py
backend/app/db/models/audit_event.py
backend/app/db/models/user.py
backend/app/main.py
backend/app/schemas/auth.py
backend/app/services/accounts.py
backend/app/services/auth_delivery.py
backend/app/services/auth_oidc.py
backend/requirements-linux.lock
backend/requirements.txt
backend/tests/test_foundation.py
backend/tests/test_phase5b.py
backend/tests/test_phase5c.py
backend/tests/test_phase5d.py
backend/tests/test_phase_f_auth.py
backend/tests/test_phase_f_postgres.py
docs/phase_f_authentication.md
```
