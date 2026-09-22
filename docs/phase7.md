# Phase 7 — sovereign local deployment and runtime proof

## Scope

IMPLEMENTED: application-level local/on-prem sovereignty controls.

NOT CLAIMED: absolute firewall/physical network isolation. Application settings
and counters cannot attest OS routing, DNS changes, filesystem mounts, another
process, or an inference server forwarding work upstream. The operator must own
and configure the private servers and network. No hosted inference adapter exists.

No Phase 8 frontend integration, Phase 9 workflow, cache, voice, multilingual,
BI, fine-tuning, new agents, n8n, or cloud deployment is included.

## Existing deployment, retained

Employee browser → existing React/Vite → FastAPI → LangGraph → existing model
gateway → host Ollama. FastAPI uses PostgreSQL and Qdrant from the existing
`infra/docker-compose.yml`, plus local `data/` and `models/` directories.

Compose already binds data services to loopback, persists PostgreSQL and Qdrant
in named volumes, and checks PostgreSQL health. It does not run the backend,
frontend, or Ollama; those remain host processes. No competing stack is added.
Do not use `docker compose down -v` unless intentionally destroying stored data.

Audit records and evidence manifests remain in PostgreSQL. Documents, OCR and
region artifacts remain under `WORKBENCH_DATA_ROOT` (default repository `data/`).
Embedding/reranker/OCR weights remain under `WORKBENCH_MODEL_ROOT` (`models/`).
No object store is required. Local path configuration does not prove a drive
isn't externally mounted or synchronized.

## Enforcement and proof

Only the existing `ollama` and `vllm` runtime choices are accepted. Ollama is
implemented; vLLM remains the existing explicit unimplemented adapter and is
**not ready**, with no fallback. Use Ollama for this demo.

Model targets require both configured allowlisting and local/private syntax:
loopback, RFC1918 IPv4, IPv6 ULA, Docker service names, and `.local`, `.internal`,
or `.svc` names. Add the exact host to `MODEL_ALLOWED_HOSTS` for LAN inference.
Public IPs/hostnames, known hosted providers, URL credentials/query parameters,
and known `:cloud`/`-cloud` model tags are rejected. DNS must resolve exclusively
to private/loopback addresses before model dispatch. Redirects and environment
HTTP proxies are disabled. DNS checking is not address pinning or a firewall.
PostgreSQL/Qdrant public configurations and cloud-URI/UNC data roots fail startup.
Qdrant HTTP transport also ignores environment proxies.

`GET /sovereignty/proof` exposes runtime, model identifier, inference/Qdrant/
PostgreSQL locality classifications, filesystem classification, hosted-config
flag, external-call count, local-dispatch attempts, observation start, timestamp,
configuration version, status, and explicit limitations. It never returns DSNs,
passwords, endpoint credentials, or environment contents.

`status=sovereign` means **no hosted AI calls observed/configured by the application
within the stated scope**, not network isolation. Counts cover dispatch attempts
through this worker's model transport; retries count separately, and restarts
reset the observation window. They are not durable audit records, cross-worker
totals, completed-inference counts, or packet capture. No HTTP counter-reset API
exists, and client fields cannot override the observations. The Phase 5 audit
chain and governance remain separate and unchanged.

`GET /health` remains inexpensive process liveness. `GET /ready` returns 200 only
when configuration is valid, PostgreSQL answers SELECT 1, Qdrant `/readyz` answers,
and Ollama's metadata endpoints report the configured model installed. Otherwise
it returns 503 with booleans, without raw errors/secrets. It performs no inference,
model download, migrations, or plant action. Individual connection/read probes
use short timeouts; OS DNS latency is outside those HTTP timeout guarantees.
Readiness does not certify corpus availability, model quality, or GPU capacity.

## Windows PowerShell startup

Prerequisites: Docker Desktop running, Python matching the existing backend
environment (Python 3.10+), Node/npm, and host Ollama installed. Start from the
repository root. Do not overwrite an existing `.env`.

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env: MODEL_RUNTIME=ollama, MODEL_NAME=qwen3.5:9b,
# MODEL_BASE_URL=http://127.0.0.1:11434. Match DATABASE_URL to Compose credentials.
# Defaults are for loopback development only; replace credentials for deployment.
docker compose --env-file .env -f infra/docker-compose.yml up -d postgres qdrant
docker compose --env-file .env -f infra/docker-compose.yml ps
ollama list
# If Ollama is not already running, run `ollama serve` in its own terminal.
# Provision once while downloads are permitted (or import pre-staged weights):
ollama pull qwen3.5:9b

Set-Location backend
if (!(Test-Path .venv/Scripts/python.exe)) { py -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
# Provision only missing model artifacts before offline operation:
.\.venv\Scripts\python.exe -m scripts.download_models --docling
.\.venv\Scripts\python.exe -m scripts.download_reranker
.\.venv\Scripts\python.exe -m scripts.download_pid_models

# Runtime: local artifacts only; disable optional tracing and hub lookups.
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:LANGCHAIN_TRACING_V2='false'
$env:LANGSMITH_TRACING='false'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Dependency/weight installation uses network provisioning, distinct from runtime
inference. Existing artifact loaders fail when required local weights are absent.
For an offline machine, transfer the prepared environments/artifacts beforehand.
Do not rerun downloads in the offline runtime terminal.

Second terminal, starting at repository root:

```powershell
Set-Location frontend
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# VITE_API_BASE_URL=http://localhost:8000 (same browser hostname for cookie use)
npm ci
npm run dev -- --host 127.0.0.1
# Open http://localhost:5173
```

Third terminal, repository root:

```powershell
backend/.venv/Scripts/python.exe backend/scripts/validate_local_runtime.py
if ($LASTEXITCODE -ne 0) { throw 'Local runtime is not ready' }
# Optional build checks:
Set-Location frontend
npm run build
npm run lint
```

The validator checks live `/health`, `/ready`, and `/sovereignty/proof`, prints
JSON, and exits nonzero on failure. Use `--backend-url http://SERVER:8000` for a
company server. No inference or write operation is performed by this command.

For LAN inference, e.g. `MODEL_BASE_URL=http://192.168.10.20:11434`, add
`192.168.10.20` to `MODEL_ALLOWED_HOSTS`. Configure Ollama's listener on that
owned server and restrict access with the company's firewall. For LAN browser
access, bind FastAPI to the intended interface, set an explicit CORS origin and
matching frontend API URL. Use HTTPS and secure session cookies for deployment.
No network policy, TLS terminator, or LAN exposure is silently installed here.
