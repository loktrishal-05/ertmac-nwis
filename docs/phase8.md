# Phase 8 — frontend/backend integration

## Scope

The existing React/Vite dashboard, navigation, sidebar, palette and health hook
are retained. Pages now consume the real FastAPI API. No backend implementation,
security policy, agent architecture, Phase 9 workflow, or plant-control surface
was added. No answers are hardcoded, including P-204 answers.

## Connected APIs

| Page / capability | API |
| --- | --- |
| Account | POST `/auth/login`, GET `/auth/me`, POST `/auth/logout` |
| Dashboard | `/health`, `/ready`, `/agents/status`, reviewer `/approvals`, `/sovereignty/proof` |
| Query Console | POST `/query` |
| Agents | GET `/agents/status` |
| Approvals | GET `/approvals`, GET `/approvals/{revision}`, POST `/approvals/{revision}/decision`, GET `/approvals/{revision}/release` |
| Knowledge | POST `/knowledge/retrieve`, POST `/documents/ingest` |
| Tamper-Evident Audit | GET `/audit/log?limit=100`, GET `/audit/verify` |
| Sovereignty | GET `/sovereignty/proof`, GET `/ready`, GET `/health` |

Dashboard counts implemented routes (not running agents). Pending counts require
reviewer/admin authentication. Indexed-document count and live agent execution
count display unavailable because those APIs do not expose such metrics.
External-call counts come from the proof endpoint, with process-lifetime limits.
Refresh buttons fetch new snapshots; only process health polls every 15 seconds.
When readiness returns HTTP 503, its reported `not_ready` status remains visible
alongside the failed dependency checks.

## Query and evidence

Questions are submitted to the backend with a fresh request UUID. No model, role,
scope escalation, or approval authority is submitted. Structured S1–S7 output is
rendered as labelled fields/lists, including refusals, clarification, warnings,
citation IDs, and evidence. Full JSON remains expandable. Drawing evidence retains
revision/page/region, raw OCR, normalized candidate, and uncertainty fields.
S5 refusal, insufficient-evidence and clarification statuses also appear in a
prominent notice above the result.

Governed drafts show a prominent human-approval-required advisory notice, revision
ID, and evidence status. Local model execution can take minutes; loading remains
visible. Keep the Query Console open while waiting. Navigating away cancels the
browser request, not necessarily work already started by the backend. No automatic
POST retry is performed. Check the review queue before repeating an uncertain
submission. This minimum phase does not add persistent conversation history.

## Authentication and approval

The HTTP-only server session cookie is sent using `credentials: include`.
Passwords exist only in the login form and are cleared after submission. No token,
password, role, or authority is written to localStorage. User/role display comes
from `/auth/me`. Page-local protected data resets when the current account changes.

Reviewer/admin users load immutable revision details before deciding. Requests
contain the decision, optional comment, and expected exact revision ID. The backend
revalidates identity, role, self-approval, hashes, evidence, concurrency, and replay.
Approve/reject controls are disabled for the requester's own revision; this is a
UI convenience, not the authorization boundary. Approved revisions can be loaded
by ID for revocation or viewing the approved advisory. The release endpoint still
enforces current approval/evidence validity. There is no equipment execution button.
Loading another revision clears the previous action result and reviewer comment.

Anonymous query use is allowed as supported by the backend, with a notice that
anonymous governed requests cannot be reviewed. Sign in before requesting a draft
intended for the review queue. Reviewer accounts must be provisioned through the
existing backend process; the UI does not create accounts or grant roles.

## Availability and safety

Each request has loading, response, empty and error handling. Independent resources
fail separately; `/ready` 503 details remain visible while `/health` can stay green.
403/401 errors are shown without bypassing access controls. React text rendering
is used for all returned content; there is no raw HTML injection or execution of
links/scripts found in model output. Backend errors and safety refusals remain visible.

The audit page says **Tamper-Evident Audit**, shows sequence/type/time/actor and
expandable hashes/payload, and displays verification validity independently.
The sovereignty page shows actual runtime/model/storage classifications, hosted
configuration, dispatch counts, observation window and backend limitations. It
does not claim OS/firewall isolation.

Knowledge search displays source content/citations. Optional ingestion names a
PDF already under backend `data/raw`; it is not a browser upload or cloud upload.
The backend validates the local path and returns indexed/duplicate/OCR-required
status. This minimum interface labels ingested PDFs as `other`; specialist metadata
and the existing P&ID processing API remain available in backend `/docs`.

## Run locally

Follow [Phase 7](phase7.md) for PostgreSQL, Qdrant, Ollama and backend startup.
Use the same hostname in browser and API configuration for same-site cookies:

```powershell
# Repository root, backend already running at http://localhost:8000
Set-Location frontend
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# frontend/.env: VITE_API_BASE_URL=http://localhost:8000
npm run dev -- --host 127.0.0.1
# Open http://localhost:5173 (not a different hostname).
```

Restart Vite after environment changes. For LAN/TLS deployment use the explicit
Phase 7 CORS and secure-cookie configuration. No relaxed backend CORS/security
settings were introduced for this integration.

```powershell
# frontend/
node --test src/services/api.test.js src/WorkspacePages.test.js
npm run lint
npm run build
```
