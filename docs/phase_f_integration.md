# Phase F main application integration

Integrated authentication commit `1e9012296839895ac477c82d2aeb2c80b4b2b734`
onto main frontend baseline `1a35075`. All 21 imported backend files match that
validated commit. No AI, RAG, agent, landing, stylesheet, video, or auth-layout
changes were made. The newer frontend was retained; only account wiring and
the previously planned admin/profile functionality were changed.

## Local configuration and database

- Development database: `postgres:5432/sovereign_workbench`, service
  `infra-postgres-1`. Its published port remains `127.0.0.1:5432`.
- Backend remains published only at `127.0.0.1:8000`.
- Migration applied: `0016_enterprise_knowledge` → `0017_accounts_recovery`.
  Alembic metadata check reports no pending operations.
- Before migration, a custom-format PostgreSQL backup was saved privately at
  `data/phase-f-before-0017.dump`. User/session fingerprints are in
  `data/phase-f-before-0017.json`; neither file is committed.
- All four original user IDs, usernames, password hashes, roles, and session
  records were preserved exactly. All four remain active. Both existing known
  development credentials were checked without changing their passwords.
- Private `frontend/.env` now uses `VITE_API_BASE_URL=/api`. The existing Vite
  proxy handles cookies on `http://127.0.0.1:5173`.
- A locally generated secret was saved only in private root `.env` as
  `WORKBENCH_AUTH_SECRET`. No secret was printed or committed.
- Capabilities: local login enabled; signup `approval`; admin recovery enabled;
  email recovery and Google disabled because their services are unconfigured.
- The original database had no administrator. `local_admin` was provisioned
  through the admin UI with a generated password saved only in ignored
  `data/phase-f-local-admin.json`. Use that private file to sign in at
  `http://127.0.0.1:5173/login` and approve accounts. The temporary smoke-test
  administrator was deactivated through the audited admin API.

## Account behavior

Signup sends only display name, normalized email, and password. Both new and
duplicate requests retain the backend's generic accepted response; no role or
activation selection is exposed. Pending accounts require administrator approval.
Login accepts an email or a preserved legacy username and uses the existing
HttpOnly, SameSite=Lax opaque session cookie. Post-login destinations remain
inside `/app`. Failed logout requests display an error instead of claiming success.

Forgot-password accurately explains the offline administrator flow when SMTP is
disabled. Email-enabled deployments get a generic request response, a link into
OTP verification, and a 60-second resend cooldown. OTP accepts either email or
legacy username. Reset capabilities remain only in React memory, expire after
10 minutes, and are cleared after use; refreshing the reset screen requires a
new code. Password-policy errors remain distinguishable from expired grants.
Successful reset redirects to login and invalidates prior sessions.

Profile shows account identity, email verification, linked providers, and real
sessions. It supports individual/all-session revocation and, when SMTP is enabled,
email verification. Administration supports paginated users, pending approvals,
creation, activation/deactivation, role changes, recovery codes, and session
revocation. Authorization and audit writes remain server-controlled.

## Live Google acceptance configuration

Google code integration and deterministic OIDC tests are complete. **Live Google
was not tested: no client credentials are configured.** For this exact local
frontend/proxy origin, configure the following in private root `.env`:

```dotenv
WORKBENCH_DEPLOYMENT_MODE=development
WORKBENCH_GOOGLE_ENABLED=true
WORKBENCH_GOOGLE_CLIENT_ID=<Google web OAuth client ID>
WORKBENCH_GOOGLE_CLIENT_SECRET=<Google web OAuth client secret>
WORKBENCH_GOOGLE_CALLBACK_URL=http://127.0.0.1:5173/api/auth/google/callback
WORKBENCH_AUTH_FRONTEND_ORIGIN=http://127.0.0.1:5173
WORKBENCH_CORS_ORIGINS=["http://127.0.0.1:5173","http://localhost:5173"]
SESSION_COOKIE_SECURE=false
WORKBENCH_AUTH_SECRET=<retain the existing private generated secret>
```

Register exactly `http://127.0.0.1:5173/api/auth/google/callback` as the Google
authorized redirect URI. Vite forwards it to backend `/auth/google/callback` on
the same browser origin as the binding/session cookie. The server then redirects
to `http://127.0.0.1:5173/auth/callback?status=...`; register the **backend proxy
callback**, not this SPA callback. Keep the browser host consistent throughout.
Restart the backend after changing its environment. New Google accounts obey
the configured signup policy, including approval. Confidential mode always
disables Google. Public deployments require HTTPS and secure cookies.

SMTP was not configured or simulated in the running development app. Live email
acceptance requires `WORKBENCH_SMTP_HOST`, `WORKBENCH_SMTP_PORT`,
`WORKBENCH_SMTP_SENDER`, `WORKBENCH_SMTP_TLS`, and any relay-required
`WORKBENCH_SMTP_USERNAME` / `WORKBENCH_SMTP_PASSWORD`. Password recovery email
requires a verified, active account. See [backend contract](phase_f_authentication.md).

## Validation

- Targeted auth/OIDC and real PostgreSQL migration/concurrency: **47 passed**.
- Security: **28 passed**.
- Full integrated Linux backend: **937 passed, 0 failed, 0 errors, 1 skipped**
  (938 total; existing opt-in live-model query skipped).
- `pip check`: no broken requirements.
- Frontend lint: zero errors; existing session-module Fast Refresh warnings only.
- Frontend: **33 tests passed**, production build passed.
- Playwright Chromium exercised the real loopback app: signup, normalized
  duplicate protection, pending login rejection/approval, wrong password, email
  and legacy login, intended redirect, cookie/refresh persistence, logout,
  profile, offline recovery notice, admin-issued OTP, invalid OTP, password reset,
  old-password/session invalidation, role changes, session revocation,
  deactivation/reactivation, admin UI account creation, and Google-disabled behavior.
- Provider-free browser checks separately mock HTTP responses to test the email
  request/OTP handoff/cooldown, enabled Google link, failed/pending callback
  messages, and disabled signup. These are **not live email or Google tests**.
- Browser harness repairs: accept a preserved `next` query on logout; check
  the input's disabled behavior rather than Playwright's fieldset predicate.
  The latter check was rerun separately to avoid consuming real signup budgets.
- Test accounts use synthetic identities and are deactivated after testing.
  Original users are not reset or deleted. Test audit history is retained.

The isolated Linux checkout passes **168/168 frozen benchmark SHA-256 checks**.
The main working tree already contained an unrelated edit to
`benchmark/reports/final_model_runtime_readiness.json` (a runtime-only qwen3.5:4b
health entry); its direct working-tree integrity check therefore fails. That
pre-existing edit is preserved and excluded from this integration commit.
No benchmark cases were executed. **BLIND was not executed.**

### Reproduce safely

Use `infra/docker-compose.auth-test.yml` with project name `phase-f-integration`.
It has a disposable `auth_test` PostgreSQL database on an internal Docker network;
it neither publishes database ports nor mounts development data. Clone a Git
bundle into `/validation/repo` in its `tests` container before testing. Do not run
the backend suite against `sovereign_workbench`.

```powershell
git bundle create data/phase-f-integration.bundle HEAD
docker compose -p phase-f-integration -f infra/docker-compose.auth-test.yml up -d
docker compose -p phase-f-integration -f infra/docker-compose.auth-test.yml exec -T tests git clone /source/data/phase-f-integration.bundle /validation/repo
docker compose -p phase-f-integration -f infra/docker-compose.auth-test.yml exec -T tests python -m alembic -c backend/alembic.ini upgrade head
docker compose -p phase-f-integration -f infra/docker-compose.auth-test.yml exec -T tests python -m unittest discover -s backend/tests -v
docker compose -p phase-f-integration -f infra/docker-compose.auth-test.yml exec -T tests python -m scripts.frozen_integrity
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build
```

`frontend/scripts/auth-smoke.mjs` uses an installed Playwright runtime (set
`PLAYWRIGHT_MODULE` to its module URI if it is not available by package name),
`AUTH_SMOKE_FIXTURE` pointing to a private JSON file containing a dedicated local
test admin's `username` and `password`, and `AUTH_SMOKE_REPORT` for the output.
It defaults to the loopback origin above, expects approval/open signup, admin
recovery, Google disabled, and the existing synthetic `dev_requester` credential.
It creates and deactivates a test signup; run it only on the local development
database. `AUTH_SMOKE_UI_ONLY=1` reruns the provider-free UI checks independently.
The private admin fixture must be provisioned/deactivated separately. Rate limits
remain enabled; do not repeatedly rerun the live smoke inside their windows.
