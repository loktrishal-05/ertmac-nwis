# Backend — Phase 4A

Current local startup, readiness, and sovereignty controls:
[Phase 7 deployment guide](../docs/phase7.md). Earlier phase descriptions below
are historical; use `/docs` for the current authenticated API contracts.

A local model gateway abstracts a swappable local inference runtime (Ollama in
development) behind a policy layer with no generation endpoint yet. See the
[Phase 4A guide](../docs/phase4a.md) and the "Local model gateway" section below.

Maintenance/sensor CSV ingestion and read-only query APIs are available at
`/data/maintenance/ingest`, `/data/sensors/ingest`, `/maintenance/*`, and
`/sensors/*`. See the [Phase 3C guide](../docs/phase3c.md).

Hybrid retrieval and optional local BGE reranking extend `/knowledge/retrieve`.
Read the [Phase 3B2 guide](../docs/phase3b2.md) before enabling sparse retrieval
on an existing collection: explicit verified migration and reranker download are
required. `/documents/pid/{document_version_id}/index` indexes stored OCR text.

P&ID PDF/image OCR preparation is available at `POST /documents/pid/process`.
See the [Phase 3B1 guide](../docs/phase3b1.md) for local PaddleOCR setup, request
examples, coordinate conventions, artifacts, and limitations. OCR does not
establish process topology. This path does not add OCR text to Qdrant.

Document extraction, local embeddings, Qdrant indexing, and evidence retrieval are
implemented. See [Phase 3A setup and API guide](../docs/phase3a.md) for model
downloads, ingestion, retrieval, data conventions, and live smoke validation.

Requires Python 3.10 or newer. Run these commands in Windows PowerShell, starting
at the repository root:

```powershell
Copy-Item .env.example .env
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If the `py` launcher is unavailable, use `python -m venv .venv` instead.
The commands use the virtual environment interpreter directly, so PowerShell
activation or execution-policy changes are unnecessary. `--reload` is for local
development only. Stop the server with Ctrl+C.

In a second PowerShell terminal, verify the endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json
```

Expected response:

```json
{
  "status": "ok",
  "service": "sovereign-agentic-workbench-backend"
}
```

Interactive API documentation: <http://127.0.0.1:8000/docs>.

## Configuration

Settings use `pydantic-settings`. The optional `.env` is loaded from the repository
root regardless of the working directory. System environment variables take
precedence. `.env` is ignored by Git; `.env.example` contains no secrets.

`WORKBENCH_CORS_ORIGINS` is a JSON array of allowed origins. Defaults allow
`localhost` and `127.0.0.1` on ports 5173 and 3000 for a future React frontend.
GET and POST are permitted through CORS, with credentials disabled.

Direct dependencies include FastAPI, Uvicorn, pydantic-settings, SQLAlchemy 2.x,
psycopg (binary), Alembic, qdrant-client, Sentence Transformers, Docling, PyMuPDF,
and httpx (promoted to a direct pin in Phase 4A; previously only a transitive
dependency of the test client). No answer-generation endpoint exists yet.

## Local model gateway (Phase 4A)

Install [Ollama](https://ollama.com) and pull a model, then discover its exact
tag — never guess it:

```powershell
ollama pull qwen3.5:9b
ollama list
```

Set `MODEL_NAME` in the root `.env` to the exact tag from `ollama list` (there
is no default; startup fails with a clear message if it is missing). Defaults
for `MODEL_RUNTIME`, `MODEL_BASE_URL`, `MODEL_ALLOWED_HOSTS`, and the other
`MODEL_*` variables in `.env.example` work for a local Ollama install without
further changes. Check status once the backend is running:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/models/status | ConvertTo-Json -Depth 5
```

See [docs/phase4a.md](../docs/phase4a.md) for the gateway/runtime split, the
structured-output contract, the host allowlist/denylist, and the error/retry
policy.

## PostgreSQL and migrations

Start Docker Desktop's Linux engine first. From the repository root:

```powershell
docker compose -f infra/docker-compose.yml config --quiet
docker compose -f infra/docker-compose.yml up -d --wait
docker compose -f infra/docker-compose.yml exec postgres psql -U postgres -d sovereign_workbench -c "SELECT 1;"
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
```

Set `DATABASE_URL` in the root `.env` to a `postgresql+psycopg://` URL. The
example uses development credentials only. `DATABASE_URL` has no `WORKBENCH_`
prefix. If overriding Compose's `POSTGRES_PASSWORD`, update the URL to match.
Use `127.0.0.1` for the local Docker database, matching `.env.example`. Both
Alembic and application database connections use a five-second connection timeout
(configurable with `WORKBENCH_DATABASE_CONNECT_TIMEOUT`, from 1 to 30 seconds).
Alembic prints its resolved target with the password hidden. The repository-root
`.env` path is absolute and works from `backend/` or, using
`-c backend/alembic.ini`, from the repository root. Process environment variables
still override `.env` values.
The Compose service binds only to 127.0.0.1:5432 and persists data in a named
volume. Changing the password variable does not change an already initialized
database's password.

Alembic owns schema creation; application startup never creates tables or applies
migrations. The initial migration defines users, agents, agent_actions, documents,
equipment, sensor_readings, incident_reports, approvals, and audit_logs.
UUID primary keys are generated by SQLAlchemy on insert. Timestamps use timezone
aware PostgreSQL types; `Agent.updated_at` updates on SQLAlchemy-issued updates.
Foreign keys connect actions to agents, sensor readings/incidents to equipment,
and approvals to actions and requesting/reviewing users. Audit event data uses
JSONB; nullable hash fields reserve space without implementing a hash chain.

The session dependency closes sessions and rolls back uncommitted work. Future
write services must explicitly commit. Placeholder routes do not access the
database, so `/health` reports process liveness even when PostgreSQL is stopped.

## Foundation API

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Original Phase 0 health JSON |
| POST | `/query` | Validates a nonempty `query`; returns `not_implemented` |
| GET | `/agents/status` | Five planned agents with `not_started` status |
| GET | `/approvals` | Empty list |
| POST | `/approvals/{approval_id}` | Validates UUID; returns `not_implemented`; no body required |
| POST | `/documents/ingest` | Validates a local raw PDF path; extracts and indexes evidence |
| POST | `/knowledge/retrieve` | Returns dense-retrieved chunks and stored citations |
| GET | `/audit/log` | Empty list |
| GET | `/sovereignty/proof` | Configuration and process-scoped gateway observations; no firewall attestation |
| GET | `/ready` | PostgreSQL, Qdrant, and installed local-model readiness; no inference |

Placeholders return HTTP 200, with `not_implemented` where applicable. Invalid
query input and malformed approval UUIDs return 422. Empty lists are placeholders,
not database queries. Phase 7 replaces the static sovereignty declaration with
application-level configuration/dispatch evidence, not OS/network attestation.
No authentication, review logic, answer generation, or agent execution exists.

## Validation

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app alembic scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m alembic upgrade head --sql
```

Tests start a temporary Uvicorn server, check API contracts/CORS, and render the
initial PostgreSQL migration offline. Offline SQL checks do not test an actual
PostgreSQL connection or apply a migration. Run the Docker and online Alembic
commands above separately when the Docker engine is available. Model-gateway
unit tests use `httpx.MockTransport`; no live model or network call is made.

Opt-in live smoke scripts (each needs its own live dependency: Ollama running
with `MODEL_NAME` installed; PostgreSQL/Qdrant up per the section above):

```powershell
.\.venv\Scripts\python.exe -m scripts.smoke_model_gateway
.\.venv\Scripts\python.exe -m scripts.smoke_knowledge
.\.venv\Scripts\python.exe -m scripts.smoke_pid --fresh
.\.venv\Scripts\python.exe -m scripts.smoke_hybrid
.\.venv\Scripts\python.exe -m scripts.smoke_structured --fresh
```

Run them sequentially, not in parallel — they compete for CPU and some compare
global point/row counts. See [docs/phase4a-validation.md](../docs/phase4a-validation.md)
for real timings recorded on development hardware.
