# E1 final backend, security and release audit

Audit date: 2026-09-30. Isolated worktree `C:\Users\Lohith k\Desktop\ertmac-nwis-e1`, branch `audit/nwis-e1-release`, initial HEAD `56e7343e0446e45bb948ccdd9354192b01b551ae`.

Accepted sources: frozen B2 `70f9060`; C2 `e988cc36b3c7f3e9b14b5d7f2ace58335d34e705`; D2 `56e7343e0446e45bb948ccdd9354192b01b551ae`; frontend baseline `579de87`. Frontend/D1 was not audited or changed. No application code, migrations, API contract or risk semantics changed. The request ended mid-item at "eligible unverified de"; this audit applies the previously accepted B2 eligibility correction and makes no assumptions about further missing requirements.

## Decision

Backend/security regression gate passes after correcting one stale migration-test assertion. The local golden demo and least-privilege application database role pass. Public deployment remains gated on accepted Claude frontend/auth SHA, TLS gateway and real public browser smoke. Google sign-in is implemented but deliberately unavailable in D2; enabling it requires the explicit checklist below. No deployment, push, merge, real administrator credential, hosted inference or held-out benchmark was used.

## Exact test results

| Suite | Final distinct passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| `test_nwis` | 27 | 0 | 0 |
| `test_nwis_b2` | 12 | 0 | 0 |
| `test_nwis_c2` | 5 | 0 | 0 |
| `test_nwis_postgres` (real PostGIS) | 6 | 0 | 0 |
| `test_nwis_retrieval` (five fixture tests plus one real BGE/Qdrant test) | 6 | 0 | 0 |
| `test_phase5b.AuthHTTPTests` | 14 | 0 | 0 |
| `test_phase_f_auth` | 39 | 0 | 0 |
| `test_phase_f_postgres` (real PostgreSQL account races) | 8 | 0 | 0 |
| `test_phase11_security` | 6 | 0 | 0 |
| `test_phase5f_security` (real PostgreSQL RBAC/session/audit/release races) | 22 | 0 | 0 |
| New `test_nwis_e1_security` | 3 | 0 | 0 |
| **Backend total** | **148** | **0 unresolved** | **0 remaining** |
| D2 stdlib preparation tests, separately | 3 | 0 | 0 |

Counts consolidate successful targeted reruns, not a claim that every test passed on its first execution. Initial authoritative-source sweep: **145 run, 143 passed, 1 failed, 1 skipped**, 410.647 seconds. The skipped real-model test was separately enabled and passed (163.446 seconds). The failure was a stale test expectation of `0017_accounts_recovery` after upgrading to the current `0018_nwis` head. Only the test now uses Alembic's repository head; all eight PostgreSQL account tests then passed (12.414 seconds). No migration was edited. Three new E1 boundary tests passed (8.856 seconds). Three preparation tests passed (1.206 seconds). Across these completed unittest invocations: 160 executions, 158 passes, one resolved failure and one subsequently executed skip; **151 distinct final passing cases** including preparation checks.

An earlier cached-image runner was stopped after detecting missing B2/C2 test modules; its incomplete run is excluded. The corrected runner mounts this E1 backend read-only. NWIS spatial tests create/drop only their own random `nwis_validation_*` databases. Account/security tests create/drop only their own random schemas. No shared runtime databases were used or modified.

Other executed checks:

- Fresh migration upgrade to `0018_nwis`; `alembic check`: **No new upgrade operations detected**.
- Real local HTTP golden smoke: **63 API checks plus ten authorized PDF/hash checks passed**; no FastAPI dependency overrides.
- Runtime validator: readiness, two repeat seeds, PostGIS/GiST/ST_DWithin/order, source integrity, Qdrant and local model artifacts passed.
- Disposable real Nginx test: syntax, **15 supported routes**, **eight denied paths**, Origin/Cookie/query forwarding, Secure Set-Cookie and no-store passed.
- Fresh public-mode configuration probe: exact credentialed CORS, hostile preflight, hostile mutation, missing-Origin browser mutation and disabled optional auth checks passed.
- `pip check`: **No broken requirements found**. This is dependency consistency, not a comprehensive vulnerability-database scan.

## Reproduction and runtime isolation

This audit uses D2's Compose plus an ignored local override, project `nwis-e1-audit`. Cached backend dependency image: `ertmac-nwis-backend:local`; serving and migration/test processes mount only E1's `backend/` read-only at `/workbench/backend`. Dedicated PostgreSQL, Qdrant and data volumes belong to this project. Existing local model artifacts are mounted read-only. The application uses D2's `nwis_app` DML role; migrations and schema/database-creating tests alone use `nwis_owner`.

The audit-only override publishes FastAPI on `127.0.0.1:8015` and the allowlisted gateway on `127.0.0.1:8014`. It sets development mode and non-Secure cookies solely for the C2 local HTTP smoke/provisioning safety check. These override values are not release settings. The separate public-mode probe and E1 HTTPS TestClient test validate release CORS/Secure-cookie behavior; actual public TLS proxy/browser validation remains pending. D2's committed release profile still has public mode, Secure cookies and only a loopback gateway port.

```powershell
Set-Location 'C:\Users\Lohith k\Desktop\ertmac-nwis-e1'
$e1 = @('-p','nwis-e1-audit','--env-file','data/e1/runtime.env',
        '-f','infra/nwis-release/compose.yml','-f','data/e1/override.yml')
docker compose @e1 run --rm --no-deps -e NWIS_TEST_POSTGRES=1 -e WORKBENCH_TEST_POSTGRES=1 migrate python -m unittest test_nwis test_nwis_b2 test_nwis_c2 test_nwis_postgres test_nwis_retrieval test_phase5b.AuthHTTPTests test_phase_f_auth test_phase_f_postgres test_phase11_security test_phase5f_security -v
docker compose @e1 exec -T -e NWIS_TEST_RETRIEVAL=1 backend python -m unittest test_nwis_retrieval.RealRetrievalTests -v
docker compose @e1 exec -T backend python -m unittest test_nwis_e1_security -v
docker compose @e1 run --rm --no-deps migrate python -m alembic -c backend/alembic.ini check
docker compose @e1 exec -T backend python -m scripts.validate_nwis_runtime
python -B infra/nwis-release/test_preflight.py
python -B infra/nwis-release/test_gateway.py
```

`data/e1` contains ignored audit-only environment/override/logs and sanitized runtime/smoke snapshots; generated secret values were suppressed. Do not copy that environment into production or upload it. For a new operator/runtime, use the protected unique secrets and provisioning commands in [deployment_preflight.md](deployment_preflight.md). The HTTP smoke used a random private password created inside the audit container and existing `provision_nwis_demo.provision`; no password appears in committed outputs. No admin was provisioned: application database admin-account count was **0**.

## Security findings

| Area | Observed control / result |
| --- | --- |
| Committed secrets | Credential-pattern scan of 791 tracked text files found zero private-key, Google secret/API key, GitHub/AWS/Slack/OpenAI credential or JWT-pattern hits. Current tracked `.env` files are examples only. Reachable HEAD history path check found only `.env.example` and `frontend/.env.example`; an all-ref exact `.env`/`.env.local` path check found none. This is a scoped pattern/path review, not an exhaustive forensic history or entropy scan. |
| Known passwords | Local dev seed has known requester/reviewer passwords, guarded by development mode. Tests/legacy development Compose contain clearly synthetic credentials. Do not run `seed_dev_users` against the release database. D2 requires separate nonempty generated database secrets; C2 reviewer tool prompts for 16-128-character unique password and refuses overwrites. No real admin credential found. |
| `.env` exposure | `.gitignore` excludes actual env files; backend build context excludes everything except backend and image recipe. Vercel exporter excludes env/link directories and emits `.vercelignore`. Nginx denies env/root paths. New test confirms traversal request does not return database configuration. |
| Debug/API surface | FastAPI has ordinary docs/OpenAPI locally, default debug disabled. D2 gateway blocks docs/OpenAPI, legacy routes, admin, ingestion and signup/recovery. Backend itself stays private; do not publish its direct audit-only port in release. |
| CORS / CSRF | Exact origin allowlist, credentials enabled; hostile mutation Origins rejected; Referer fallback checked; browser requests carrying Sec-Fetch-Site without Origin/Referer denied. Headerless non-browser callers are allowed but still require valid sessions/RBAC. No claim of a separate synchronizer CSRF token. SameSite=Lax plus origin checks preserve OIDC redirects. No wildcard production CORS. |
| Cookies / logout | Opaque 32-byte random session tokens, SHA-256 persisted, Argon2id passwords. Host-only Secure/HttpOnly/SameSite=Lax/path=/ in release. Logout revokes the server token; replay denied. Login rotation, expiry, per-user revoke-all, role change, deactivation and password-reset revocation covered. |
| Authority / role escalation | Server loads active/nonpending user and role through DB-backed session. Request schemas reject extra identity/role fields; signup and new Google accounts become requester, not reviewer/admin. Administration rechecks actor and serializes against competing admin changes. Real forged/stale role and release/revocation races passed. |
| PDFs / files | Authentication plus advisory terms and well visibility enforced; restricted source returns bounded 404. Source filename is validated lowercase 64-hex hash, never user path; stored bytes checked against SHA-256. Anonymous PDF test returns 401. Assessment evidence reauthorizes linked event/report wells. |
| Uploads | Admin plus terms/well access; `application/pdf`, PDF magic, 20 MiB streaming cap and 1-100-page inspection. E1 tests prove 415/413; existing invalid-PDF/native-ingest tests pass. OCR remains local and uncertain numbers review-gated. Public gateway denies ingestion entirely (1 MiB general gateway body cap is for demo API use). PDF parsing is not malware scanning or an isolated document-processing sandbox; do not enable public uploads without a separate review. |
| SQL injection | ORM and bound ST_DWithin/ST_Distance parameters; depth basis constrained to supported enum. No user-supplied executable SQL/shell in audited NWIS/auth paths. Injection-like formation value returns an empty list. Dynamic schema/database names exist only in disposable tests and derive from UUIDs. |
| Filesystem / inference | Reports content-addressed, exclusive create and hash checks. Model/data roots local; BGE artifacts read-only; local model endpoints allowlisted and private-resolution checked. No hosted proprietary inference. |
| Service exposure | E1 PostgreSQL/Qdrant have no published host ports; release storage network internal. Inspected host listeners for PostgreSQL, Qdrant, Ollama and audit HTTP ports were `127.0.0.1`. Ollama 11434 remained loopback-only and reachable from Docker. No tunnel/deployment was started. This is local configuration/listener evidence, not an external port scan. |
| Error leakage | Auth/admin 422 response omits submitted inputs; login/recovery generic failure behavior tested; OIDC errors do not reveal provider bodies; callback query stripped from ASGI access-log scope. Readiness exposes booleans, never credentials/connection bodies. Query dependencies return bounded 503; report/unknown-well errors bounded. Replay ValueError messages are fixed validation explanations. |
| Audit / provenance | Database audit immutability/truncation/tamper and transaction-failure prevention tests passed. Reviewer NWIS audit constrained to actor; source/event state snapshots remain visible. Credentials and recovery/session tokens absent from tested audit payloads. |

Remaining operational limits: shared gateway IP means B2's 30-login/15-minute IP budget is shared; a supervised limited audience is assumed. Gateway rate limiting is global, not a per-user inference quota. Hybrid retrieval can consume CPU; no HA/DoS guarantee is claimed. Backup protection, operator Docker access, TLS provider account and postdeployment browser behavior still need release execution checks.

## Google OIDC backend: exact readiness checklist

Read-only backend audit and generated-key/provider-mocked tests passed; **no live Google login or credentials were used**. Existing `/auth/google/start` and `/auth/google/callback` return 404 with D2's disabled configuration. Do not mark Google production-ready merely because unit tests pass.

| Backend property | Status |
| --- | --- |
| Authorization-code flow | Authlib client, `openid email profile`, fixed HTTPS Google endpoints |
| PKCE | S256, verifier HMAC-derived per random state, verifier sent only during server token exchange |
| State | Cryptographic random state; hash stored; 10-minute expiry; row locked and consumed before exchange; replay fails |
| Nonce | Separate HMAC purpose, tied to state; required ID-token claim and exact expected value |
| Browser binding | Independent random HttpOnly/Secure/Lax binding cookie; stored hash compared in constant time; missing/wrong binding fails |
| Callback URI | Fixed configured redirect URI used in authorization and exchange; HTTPS outside loopback development; no user return-URL accepted |
| Token validation | RS256-only signature using Google JWKS; issuer, audience, expiry, issued-at, subject and nonce essential; azp/multiple-audience checks, verified email, bounded subject; normalized email required |
| Provider requests | Verified TLS; no redirects; no environment proxies; 10-second timeout; 1 MiB streamed response cap |
| Persistence | Identity stores provider/subject/user link; flow stores only hashes/time. Provider access, refresh and ID tokens are not persisted or included in audit. No offline-access scope requested. |
| Existing-account linking | Requires locally verified email; differing/unverified identity not silently merged. New account obeys signup mode and receives requester role only. |
| Session issuance | Backend session replaces previous token; pending/inactive account gets no session; binding cookie cleared; frontend receives only bounded status redirect |

Claude/deployment must satisfy ONE declared release policy:

1. **Local-reviewer demo:** leave Google disabled as D2 currently does. Frontend must honor `/api/auth/capabilities` and handle unavailable signup/recovery/Google consistently. No backend OAuth or public routing change is necessary.
2. **Google-enabled release, if explicitly selected:** provide `WORKBENCH_GOOGLE_ENABLED=true`, `WORKBENCH_GOOGLE_CLIENT_ID`, operator-private `WORKBENCH_GOOGLE_CLIENT_SECRET`, `WORKBENCH_GOOGLE_CALLBACK_URL=https://sovereign-ai-workbench-nine.vercel.app/api/auth/google/callback`, and unique `WORKBENCH_AUTH_SECRET` of at least 32 bytes. Keep `WORKBENCH_DEPLOYMENT_MODE=public`, `SESSION_COOKIE_SECURE=true`, exact `WORKBENCH_AUTH_FRONTEND_ORIGIN` and `WORKBENCH_CORS_ORIGINS`. Register the exact callback URI in the Google Web application and satisfy consent/test-user requirements. This backend uses AUTH_SECRET for both OIDC derivation and recovery capabilities, so enabling Google also changes reported recovery capability; SMTP remains absent unless separately provisioned. Review that capability/UI interaction explicitly.
3. For Google-enabled release only, D2 gateway requires narrow allowlisting of `/api/auth/google/start` and `/api/auth/google/callback`, stripping `/api` once. Vercel already preserves the public API prefix. **No such configuration change was made in this audit.** Google callback must land on the SAME public browser origin that set the binding cookie; do not configure the tunnel origin as redirect URI.
4. Frontend starts a full browser navigation to `/api/auth/google/start` and handles `/auth/callback?status=success|pending_or_inactive|failed`. Backend never redirects to a user-supplied destination. Claude owns these UI behaviors; E1 neither inspects nor modifies them.
5. With signup disabled, a new Google subject cannot self-provision. An explicitly provisioned, email-verified allowed account must exist; the local username-only demo reviewer is not automatically Google-linkable. Do not open signup or promote new Google accounts to reviewer/admin to bypass this.
6. Execute real public TLS start/callback/session smoke after configuration and frontend acceptance, including denied/replayed/missing-binding cases. Never log callback codes/state or copy provider tokens to the frontend/storage.

Protocol expectations checked against [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect) and [Authlib HTTP clients](https://docs.authlib.org/en/stable/oauth2/client/http/index.html). These sources support the protocol checklist; runtime findings above come from repository inspection and local tests.

## Risk and safety invariants

- `app/services/nwis.py` computes exposure/probability/confidence directly from authorized relational evidence and telemetry; it never calls an LLM. `app/agents/nwis.py` uses deterministic evidence templates; BGE/reranking ranks citations only, not probability.
- Probability and confidence remain separate. No usable analogs retain null probability, not zero/fabricated estimates. Missing-depth, TVD/TVDSS, stale telemetry and low-confidence behavior pass existing suites.
- `calibrated=false`, `advisory_only=true`, synthetic origin and engineering-review terms remain. No NWIS actuator/rig-control tool exists; injection/operational requests refused. Legacy endpoints are not public through the NWIS gateway.
- Rejected and review_needed events excluded. Confidence below .5 excluded even if human-validated. Clean unverified events at/above .5 may contribute under B2 eligibility; they remain unverified after query, assessment and advisory acknowledgement. Only explicit human event validation changes that state; reviewer/time/reason audited.
- Assessment snapshots preserve the event state/confidence and source hashes actually used. Current event state stays separately visible. Source links retain `#page=`. Advisory acknowledgement is distinct from source validation.
- Alert policy unchanged: three eligible assessments, trigger .6, clear .4, 30-minute cooldown and deterministic well/hazard/interval identity. Golden replay produced [0,0,2] new advisories; duplicate assessment produced none. Unit tests cover transient reset, hysteresis, clear, cooldown and dedupe.

Golden ACTIVE-01: MD 2450 m, TIPAM_A, 100 m window. Closest OFF-01; strongest analog OFF-04. Stuck-pipe probability **0.7455033407089751**, confidence **0.855**, historical exposure **0.7005921655399706**, telemetry contribution **0.15**, calibration false. Seven supporting offsets: OFF-03/OFF-04/OFF-05/OFF-06/OFF-09/OFF-10/OFF-11. All canonical values and ten evidence IDs match [golden_demo_fixture.json](golden_demo_fixture.json).

Observed chain example: `EVT-00b7d3f0d01482cb574dc230e1972ddc` -> `OFF-04-DDR` -> page **5**, source hash `365c881c6387d4ecf4bbcab500dd2221d2fbdc49754358d048d29610179551c6` preserved in assessment. Assessment `1082674d59e85dc8b1f57843ddb690ef92c23f5e565e1665358a036ad1b9abd7` -> advisory acknowledgement -> reviewer `459dc367-2a56-472e-8b9a-9720c68d1ba8` at `2026-09-30T06:44:28.947785Z` -> own audit. Final audit chain: **22 entries**, valid, sequence 1..22, head `55b08113469c881a6e64528215c233f2c5ef061221a86949a0a06ea5d8e061a7`. These are audit-run identities, not frontend constants.

## Release runtime and performance results

Readiness HTTP 200; fastapi/configuration/postgresql/qdrant/model true. Qwen check proves reachability and installed `qwen3.5:9b`, not generation. BGE embedding/reranker inference and HTTP hybrid retrieval are real. PostgreSQL 17/PostGIS 3.5.2, migration `0018_nwis`, GiST index and deterministic nearby SQL/order pass. Collection `nwis_evidence_v1` green, 66 points. Repeat seed retained 12 wells, 396 trajectory points, 48 formations, 11 reports, 66 events and 610 samples; all 11 source PDFs matched hashes. Telemetry replay channels fresh relative to `2026-09-29T16:00:00Z`, not today's wall clock.

Local median milliseconds during concurrent regression/retrieval load: wells **52.17**, nearby **1104.47**, correlation **1346.21**, risk **1597.85**, assessment **342.30**, telemetry **400.38**, hybrid query **11006.08**. This is load-contended audit evidence, not an isolated benchmark or public latency guarantee. Prewarm and verify an unloaded public warm median below the frontend's 30-second timeout before judge use. No held-out cases were opened or run.

## Remaining deployment gates

Accepted final Claude D1/auth commit and its build/tests; declared local-only versus Google-enabled policy; reserved HTTPS gateway and operator credentials; protected production secrets; reviewed Vercel project settings; final exported artifact; fresh release-volume migration/seed/index validation; actual same-origin HTTPS cookie/callback/PDF/browser smoke; backup and rollback identity record; warm public latency check. Existing [deployment_preflight.md](deployment_preflight.md) remains the deployment order and rollback plan.

No unresolved backend regression or B2 contract blocker found. The scoped security review found no demonstrated credential disclosure or privilege escalation in the tested NWIS path. Public deployment and live Google login have NOT been validated. E1 changes are limited to three security tests, a corrected migration-test expectation and this audit record; no frontend/UI/application/migration changes.
