# Phase 9: P-204 advisory demonstration

This is a synthetic software demonstration, not MRPL data or an operating procedure.
It uses the ordinary query, LangGraph, retrieval, local inference, governance,
approval and audit paths. There is no demo answer endpoint or equipment execution.

## Startup (Windows PowerShell)

Start from the repository root with the existing environments and local model
artifacts provisioned as described in Phase 7. Preserve the existing `.env`.

```powershell
docker compose --env-file .env -f infra/docker-compose.yml up -d postgres qdrant
docker compose --env-file .env -f infra/docker-compose.yml ps
ollama list
# Start `ollama serve` in a separate terminal only if Ollama is not running.
# MODEL_RUNTIME=ollama and MODEL_NAME=qwen3.5:9b in the existing root .env.
Set-Location backend
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:LANGCHAIN_TRACING_V2='false'
$env:LANGSMITH_TRACING='false'
$env:MODEL_MAX_OUTPUT_TOKENS='2048'
$env:MODEL_TIMEOUT_SECONDS='900'
$env:AGENT_RUN_TIMEOUT_SECONDS='2000'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m scripts.seed_phase9
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The seed command runs the existing ingestion handlers with real local PDF
extraction/embeddings and OCR. It imports one SOP, three maintenance rows, five
sensor readings and a synthetic P&ID label excerpt, then indexes the OCR. Repeating
it reuses immutable sources and existing duplicate detection; it does not reset
the database or rewrite an existing user. Run it only in the local demo environment.

Second terminal, repository root:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1
# Open http://localhost:5173; API URL must also use localhost for cookies.
```

Third terminal, repository root:

```powershell
backend/.venv/Scripts/python.exe backend/scripts/validate_local_runtime.py
```

Readiness must show ready before presentation. It checks dependencies, not answer
quality; perform a rehearsal using the validation command below too.
The successful local rehearsal took 487.6 and 409.4 seconds per query on this
host. Allow about 7–9 minutes for each query here; this is observed performance,
not a guaranteed upper bound. Do not promise an instant response during SIH.
The frontend/validator allow 2,100 seconds for a query. The process overrides above
allow up to 2,000 seconds overall and 900 seconds per warmed model call so that
generation plus the existing bounded repair can finish on this mostly CPU host.
Keep the backend budget below the client wait. These limits are not a latency
guarantee; a presentation needs a successful timed rehearsal on its actual hardware.

## Local demonstration accounts

The importer creates these dedicated accounts only if absent:

| Account | Password | Server role |
| --- | --- | --- |
| phase9_requester | phase9-requester-local-only | requester |
| phase9_reviewer | phase9-reviewer-local-only | reviewer |

These are deliberately public local-demo credentials, never production credentials.
The importer refuses to overwrite an existing account whose role/password differs.
Self-approval remains prohibited. The backend checks every decision's identity.

## Presentation sequence

1. Open Dashboard. Show backend Connected, readiness ready, local model and sovereignty.
2. Sign in as `phase9_requester`, then open Query Console. Type exactly:

   > Pump P-204A vibration is elevated. Review the available sensor data, maintenance history, SOP and P&ID evidence and advise what should be done.

3. Submit once. Show the loading state. Inference can take minutes on this machine;
   do not navigate away or resubmit while waiting. A timeout does not prove that
   backend work was cancelled; check the review queue before repeating it.
4. Expected route: `combined_safety_maintenance`. This is the existing combined
   Safety handler, with Maintenance history/sensor tools and Knowledge retrieval.
   Do not describe it as three independent agents executing concurrently.
5. Show the actual output's observations, tentative hypotheses, limitations and
   citations. The imported historical sensor window is **2026-09-16 10:00–10:20 UTC**:
   3.1, 3.3, 3.4, 3.5, 8.2 mm/s. The synthetic SOP alert is 7.1 mm/s; high-high
   is 11.0 mm/s. An alert crossing does not prove a cause or a high-high crossing.
6. Expand source evidence: SOP-P204-001, MH-P204 work orders, SENSOR-P204-A
   provenance, and PID-U2-017 R3 regions where retrieved. Show raw OCR separately
   from normalized candidates. This drawing is an **as drawn label excerpt**, not
   an actual connectivity plan, field valve state, isolation proof, or permit.
7. Show PENDING_REVIEW / DRAFT and the exact revision ID. Record the ID. Model
   wording varies; if the backend refuses, show the reason honestly. A refusal
   must not be presented as a successfully grounded advisory.
8. Sign out and sign in as `phase9_reviewer`. Open Approvals, select that revision,
   inspect the proposal, citations and integrity status, then Approve advisory.
   View approved advisory demonstrates release of text only. No control command
   is executed. Revoke approval, then verify release is denied.
9. Submit another genuine query as requester to obtain a separate draft. Reject
   it as reviewer; rejected drafts cannot be released. Do not forge a second draft.
10. Open Tamper-Evident Audit. Refresh and show approval, advisory-release,
    rejection/revocation events and chain verification VALID.
11. Open Sovereignty. Show qwen3.5:9b / Ollama, local PostgreSQL/Qdrant,
    hosted AI not configured, current-process external dispatch count, and
    explicit proof limitations. Network/firewall enforcement is not attested.

## Fallback and validation

If the broad query fails, disclose the actual failure and try the narrower query:

> What does SOP-P204-001 say about the vibration alert threshold for pump P-204A?

Expected fallback route: knowledge. This only demonstrates grounded retrieval;
it does not substitute for a successful combined advisory or approval demo.

From `backend`, the live validator submits two real model queries and exercises
approve/release/revoke and reject/denied-release using those actual drafts:

```powershell
.\.venv\Scripts\python.exe -m scripts.validate_phase9
```

Results go to `data/processed/phase9-live.json`; seed IDs/hashes go to
`data/processed/phase9-seed.json`. The validator fails if required evidence,
citations, reasoning fields, approval state or audit verification are absent.
It never replaces a failed model result with an expected answer. The script is
an HTTP test client, not an alternative inference pipeline.

## Shutdown and cleanup

Sign out of both demo accounts. Use Ctrl+C in the frontend and FastAPI terminals.
Optionally unload the model with `ollama stop qwen3.5:9b`. If no other work uses
the data services, run from repository root:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml stop postgres qdrant
```

Keep raw evidence and audit records intact for repeatability and hash verification.
Do not delete volumes, evidence files, revisions or audit records as demo cleanup.
Generated raw/processed artifacts and local logs are Git-ignored. The importer
does not change production roles, deploy the app, or commit files.
