# F1 production configuration

No secret values are recorded here. Operator inputs are read by Compose from a protected environment file; runtime names below are what FastAPI actually reads. Frontend `VITE_*` settings are embedded in public JavaScript. Build the tested commit, set `/api`, disable fixtures, and record the image ID before any separately authorized deployment.

| VARIABLE | FRONTEND/BACKEND | REQUIRED? | SECRET? | LOCAL VALUE TYPE | PRODUCTION VALUE TYPE |
| --- | --- | --- | --- | --- | --- |
| `VITE_API_BASE_URL` | Frontend | Yes, release build | No | Relative `/api` with Vite proxy | Relative `/api` with Vercel HTTPS gateway rewrite |
| `WORKBENCH_API_PROXY` | Frontend tooling | Local only | No | Loopback backend URL | Unused; Vercel rewrite supplies gateway |
| `VITE_NWIS_FIXTURES` | Frontend | Yes, release build | No | Optional development fixtures | `0`; production bundle check rejects fixtures |
| `VITE_DEMO_LOGIN` | Frontend | Optional | No | Default visible | Visible for synthetic demo; `off` for non-demo |
| `VITE_DEMO_USERNAME`, `VITE_DEMO_PASSWORD` | Frontend | Only to override public demo | No | Public synthetic reviewer credentials | Public demo only; never private credentials |
| `NWIS_GATEWAY_ORIGIN` | Frontend export/operator | Yes before export | No | Test HTTPS hostname in offline tests | Assigned DNS origin with trusted HTTPS |
| `NWIS_PUBLIC_ORIGIN` | Backend Compose/operator | Yes | No | Exact test origin | Exact HTTPS Vercel frontend origin |
| `NWIS_BACKEND_IMAGE` | Backend Compose/operator | Yes | No | Existing local validation image with release source mount | Unique immutable tag/digest built from tested final SHA |
| `NWIS_DB_OWNER_PASSWORD` | Backend migration/Compose | Yes | Yes | Disposable owner secret | Unique URL-safe migration-owner secret |
| `NWIS_DB_PASSWORD` | Backend Compose | Yes | Yes | Disposable database secret | Separate URL-safe application secret |
| `DATABASE_URL` | Backend | Yes | Yes | Dedicated private validation PostGIS URL | Private `postgres:5432/nwis`, least-privilege `nwis_app`; migrate alone uses `nwis_owner` |
| `QDRANT_URL` | Backend | Yes | No | Private validation service URL | `http://qdrant:6333`, internal storage network |
| `MODEL_RUNTIME`, `MODEL_NAME`, `PRIMARY_MODEL` | Backend | Yes | No | Ollama, installed `qwen3.5:9b` | Same pinned local model; no guessed tag |
| `MODEL_BASE_URL`, `MODEL_ALLOWED_HOSTS` | Backend | Yes | No | Local/private Ollama URL and allowlist | Local/private Ollama only; Docker host URL and explicit hostname allowlist |
| `NWIS_MODEL_DIR` | Backend Compose/operator | Yes | No | Existing absolute local BGE artifact root | Existing read-only local BGE/reranker artifact root |
| `WORKBENCH_MODEL_ROOT` | Backend | Yes | No | Container `/workspace/models` | Container `/workbench/models` |
| `WORKBENCH_DATA_ROOT` | Backend | Yes | No | Separate validation source-PDF directory | Writable persistent private data volume |
| `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `HF_HOME` | Backend | Yes | No | Offline local artifacts/cache | `1`, `1`, writable `/tmp/huggingface` cache |
| `OMP_NUM_THREADS`, `MKL_NUM_THREADS` | Backend | Supplied by release | No | `2` | `2`, limits CPU contention |
| `WORKBENCH_CORS_ORIGINS` | Backend | Yes | No | JSON array of local frontend origins | JSON array containing only approved HTTPS frontend origin |
| `WORKBENCH_AUTH_FRONTEND_ORIGIN` | Backend | Yes | No | Exact local frontend URL | Exact HTTPS frontend origin |
| `SESSION_COOKIE_SECURE` | Backend | Yes | No | `false` on HTTP; tests also exercise HTTPS `true` | `true` |
| `SESSION_COOKIE_NAME`, `SESSION_TTL_SECONDS` | Backend | Supplied by release | No | Opaque session cookie, eight hours | `workbench_session`, `28800`; HttpOnly, SameSite=Lax, host-only |
| `NWIS_AUTH_SECRET` → `WORKBENCH_AUTH_SECRET` | Backend | Yes for release OTP | Yes | Disposable random secret; existing Gmail stack secret stays untouched | Unique random secret of at least 32 bytes, from protected environment |
| `NWIS_SIGNUP_MODE` → `WORKBENCH_SIGNUP_MODE` | Backend | Default supplied | No | `open` | `open` for demo, or explicit `approval`; new role always requester |
| `NWIS_SMTP_HOST` → `WORKBENCH_SMTP_HOST` | Backend | Yes | No | Loopback Mailpit in validation; separately configured real relay in existing stack | Production SMTP provider/relay hostname |
| `NWIS_SMTP_PORT` → `WORKBENCH_SMTP_PORT` | Backend | Default supplied | No | Mailpit `1025` | `587` with STARTTLS or `465` with TLS |
| `NWIS_SMTP_TLS` → `WORKBENCH_SMTP_TLS` | Backend | Default supplied | No | `none` only on development loopback | `starttls` or `tls`; certificate validation enabled |
| `NWIS_SMTP_SENDER` → `WORKBENCH_SMTP_SENDER` | Backend | Yes | Contact/config | Synthetic local sender | Provider-authorized mailbox/From header |
| `NWIS_SMTP_USERNAME` → `WORKBENCH_SMTP_USERNAME` | Backend | If relay authenticates | Credential identifier | Empty on Mailpit | Provider account identifier |
| `NWIS_SMTP_PASSWORD` → `WORKBENCH_SMTP_PASSWORD` | Backend | If relay authenticates | Yes | Empty on Mailpit | Provider credential/App Password; never Git/Vite |
| `NWIS_DEMO_USERNAME`, `NWIS_DEMO_PASSWORD`, `NWIS_DEMO_ROLE` | Backend seed tooling | Optional public demo overrides | Public demo only | Seeded synthetic reviewer, no email | Same public credentials as frontend; only requester/reviewer; synthetic-data and collision guards |
| `WORKBENCH_GOOGLE_ENABLED` | Backend | Supplied by release | No | `false` in final validation | Hard-set `false`; gateway rejects Google endpoints |
| `WORKBENCH_GOOGLE_CLIENT_ID` | Backend | Not used in this release | No | Existing stack may have an ID | Unset; future live Google setup only |
| `WORKBENCH_GOOGLE_CLIENT_SECRET` | Backend | Not used in this release | Yes | Not copied or printed | Unset; future protected OAuth secret only |
| `WORKBENCH_GOOGLE_CALLBACK_URL` | Backend | Not used in this release | No | Local callback in developer config | Unset; future exact HTTPS `/api/auth/google/callback` URI |
| `WORKBENCH_DEPLOYMENT_MODE` | Backend | Yes | No | `development` for isolated HTTP validation | `public`; supported values are development/confidential/public |

The development Compose file translates `NWIS_GOOGLE_*` and `NWIS_AUTH_FRONTEND_ORIGIN`; the production Compose file deliberately does not pass Google credentials and derives `WORKBENCH_AUTH_FRONTEND_ORIGIN` from `NWIS_PUBLIC_ORIGIN`. Signup/recovery no longer use D2's disabled policy. OTP lifetime/attempt limits are fixed implementation values, not invented environment variables.

## Missing and invalid configuration

Production Compose rejects absent/empty auth secret, SMTP host/sender, database secrets, image, model root and frontend origin before starting. Settings rejects auth secrets shorter than 32 bytes, unknown deployment/signup/TLS literals, and TLS-free SMTP outside development loopback. Provider credentials are conditional because a protected relay can authenticate by network policy; Gmail requires both username and App Password. Missing provider credentials can fail delivery even with syntactically valid configuration, so verify inbox arrival after deployment.

Direct FastAPI startup without an auth secret keeps password login available and reports recovery/Google unavailable; OTP verification returns 503. With no SMTP host/sender, email recovery is false and requests return generic 202 without issuing codes. Delivery errors consume the issued challenge and append a redacted failure audit event; the response stays generic. The frontend enables flows only from `/auth/capabilities`; `smtp` means configured delivery, not proof that the mailbox received it. Real Gmail receipt was reported during Claude's earlier testing; F1 validates delivery in a disposable local inbox without sending another external email.

## Exposure and future deployment gates

Only Vercel → trusted HTTPS gateway → FastAPI is public. The Nginx listener binds loopback; FastAPI/PostGIS/Qdrant have no published ports in production Compose. PostGIS/Qdrant use an internal network. Ollama must remain local/private and firewall restricted. Mailpit exists only in the local validation stack and must never be publicly exposed. External SMTP transports auth mail only; local BGE/Ollama still perform retrieval/model work.

Google is implemented and covered by provider/signature/state tests, but no live Google login is claimed. Enabling it later requires a protected client secret, authorized HTTPS frontend origin and callback URI, an explicit reviewed gateway allowlist change, public-mode configuration, and a complete live cookie/callback/login test. It is outside this release.
