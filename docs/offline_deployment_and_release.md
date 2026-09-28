# Offline deployment and release

Supported topology: Linux Docker Python 3.11 CPU backend, host-local Ollama, existing Compose PostgreSQL 17 and Qdrant 1.17.0,
local files, and a locally served frontend build behind a site-managed TLS proxy. Optional STT/TTS are
local HTTP adapters. Optional n8n stays on-premise and summary-only. No Netlify deployment is involved.

This runbook supersedes earlier development startup instructions. It does not certify a site's firewall,
TLS, hardware capacity, backup retention or adapter quality. No frozen benchmark or BLIND execution is required.

## Supported Linux backend on this Windows host

Prerequisites: Git, Node 22/npm, Docker Desktop with Linux containers, Ollama, and enough RAM/VRAM
for the selected models/context. For native backup outside the bundled Compose, install PostgreSQL 17 client tools.
Use a dedicated service account and encrypted local storage. Commands start in PowerShell; no venv activation needed.

```powershell
$Repository = Read-Host 'Approved repository URL or local Git bundle path'
git clone $Repository sovereign-workbench
Set-Location sovereign-workbench
Copy-Item .env.example .env
# Configure .env as described below, then build the Linux backend.
docker build -f infra/Dockerfile.backend -t sovereign-workbench-backend:py311-cpu .
Push-Location frontend
npm.cmd ci
npm.cmd run lint
node --test src/*.test.js src/services/*.test.js
$env:VITE_API_BASE_URL = Read-Host 'Site HTTPS API origin (e.g. https://api.workbench.internal)'
npm.cmd run build
Pop-Location
$env:PYTHONPATH = "$PWD;$PWD/backend;$PWD/backend/tests"
```

Check each native command's exit status before continuing. This is installation/build work, not frontend feature work.
The release installs `backend/requirements-linux.lock`: exact direct and transitive versions from the validated Linux environment,
plus the existing local speech stack. The broad `requirements.txt` records dependency intent only. Python 3.11 on Linux x86_64
is the approved backend runtime. Torch and torchvision are pinned to `+cpu` builds from the official PyTorch CPU index;
CUDA packages are not part of this release. Frontend dependencies use the existing lockfile.
`VITE_API_BASE_URL` is embedded at build time: set it to the site's HTTPS API origin before every production build.
It is public configuration, never a secret. The proxy must route that origin to the loopback backend, with the
frontend's exact HTTPS origin in CORS. For a same-origin deployment, route API paths and static frontend paths
explicitly; the API currently uses root paths rather than a universal `/api` prefix.

Edit the ignored root `.env` using a protected editor. Set `MODEL_NAME=qwen3.5:9b`; configure local DB/Qdrant URLs,
data/model roots, production DB credentials, HTTPS CORS origins, and `SESSION_COOKIE_SECURE=true`.
Merge `infra/offline.env.example` into it, replacing existing keys rather than creating ambiguous duplicates.
Set `POSTGRES_PASSWORD` for Compose separately from the backend's `DATABASE_URL`. Compose interpolation uses root
`.env` only when `--env-file .env` is passed. Never run `docker compose config` into a public log: it resolves secrets.

### Explicit provisioning, before disconnection

On an approved connected preparation machine with the **same OS/architecture/Python**, download packages/images/models:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml pull
docker image save -o offline-images.tar postgres:17 qdrant/qdrant:v1.17.0
ollama pull qwen3.5:9b
ollama pull qwen3.5:4b
ollama list
ollama show qwen3.5:9b
ollama show qwen3.5:4b
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.backend.yml run --rm -e HF_HUB_OFFLINE=0 -e TRANSFORMERS_OFFLINE=0 -v "${PWD}/models:/workbench/models" backend python -m scripts.download_models --docling
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.backend.yml run --rm -e HF_HUB_OFFLINE=0 -e TRANSFORMERS_OFFLINE=0 -v "${PWD}/models:/workbench/models" backend python -m scripts.download_reranker
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.backend.yml run --rm -e HF_HUB_OFFLINE=0 -e TRANSFORMERS_OFFLINE=0 -v "${PWD}/models:/workbench/models" backend python -m scripts.download_pid_models
# The prebuilt backend image contains all Python and native dependencies.
docker image save -o offline-backend.tar sovereign-workbench-backend:py311-cpu
```

Ensure the wheelhouse contains compatible wheels for every dependency; build missing wheels on that preparation machine,
then rehearse `pip install --no-index` on a clean target before signing the release bundle. Preserve source revision,
`frontend/package-lock.json`, built `frontend/dist`, an npm cache prepared by `npm ci --cache ../npm-cache`, all model
artifacts, image digests, Ollama version and Ollama's complete `models` directory (manifests and blobs).
Stop Ollama before copying its model store. Use the same `OLLAMA_MODELS` location for the service account on the target.
Record SHA-256 hashes of every transferred file, verify them offline and retain an independently protected signed manifest.

On the disconnected target, transfer the Git bundle/source, wheels, frontend artifacts/cache, images and model stores:

```powershell
docker image load -i offline-images.tar
docker image load -i offline-backend.tar
# Only if rebuilding the frontend offline; otherwise deploy the approved frontend/dist.
Push-Location frontend
npm.cmd ci --offline --cache ../npm-cache
npm.cmd run build
Pop-Location
```

The application never downloads LLM weights at startup. Record `/api/tags` tag/digest/quantization and `/api/show`
context/capabilities after provisioning; set `WORKBENCH_RELEASE_MODEL_DIGESTS` to a JSON map of the two exact tags to
approved full digests. Missing primary **or fast** model is a release failure. Unpinned digests warn. Ollama metadata
verification follows its [local API contract](https://github.com/ollama/ollama/blob/main/docs/api.md).
Model presence/capacity does not prove inference speed or available RAM. Run explicitly approved synthetic smoke checks
on target hardware; the release preflight performs only the bounded synthetic retrieval runtime probe, never BLIND.

### Deterministic startup order

1. Enforce host/network controls and provision local storage, images and models.
2. Start PostgreSQL and Qdrant with the existing Compose plus offline overlay.
3. Run reviewed migrations with the migration account, then switch to the runtime account.
4. Start Ollama with cloud features disabled and loopback binding, then optional local voice adapters.
5. Run dependency preflight; start the backend only on success.
6. Serve the built frontend behind the on-premise TLS reverse proxy, then optionally start local n8n.
7. Run full release health and site browser/auth/restore acceptance.

```powershell
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.offline.yml up -d
docker compose -f infra/docker-compose.yml exec -T postgres pg_isready -U postgres -d sovereign_workbench
Invoke-WebRequest http://127.0.0.1:6333/readyz -UseBasicParsing
$env:PYTHONPATH = "$PWD;$PWD/backend;$PWD/backend/tests"
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.backend.yml run --rm backend python -m alembic -c backend/alembic.ini upgrade head
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.backend.yml run --rm backend python -m alembic -c backend/alembic.ini check
```

Use the migration account only for these Alembic commands; do not leave its credentials in the backend environment.
For a fresh dedicated database migrated by its owner, provision a separate runtime login through local psql:

```powershell
docker compose -f infra/docker-compose.yml exec postgres psql -U postgres -d sovereign_workbench
```

Inside psql, run the following once, entering the runtime password only at the hidden prompt:

```sql
CREATE ROLE workbench_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
\password workbench_app
GRANT CONNECT ON DATABASE sovereign_workbench TO workbench_app;
GRANT USAGE ON SCHEMA public TO workbench_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO workbench_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO workbench_app;
\q
```

Set the protected runtime `DATABASE_URL` to that login (URL-encode its password). Keep migration-owner credentials
in the operator's secret store; grant privileges on new tables after each reviewed migration. Do not grant this
runtime role schema creation, DELETE on audit/evidence ledgers, table ownership or ability to disable triggers.
Historical migrations 0001–0016 are unchanged. `python -m scripts.validate_migrations` tests a fresh schema, a
0015-to-head upgrade and repeated head upgrade in disposable schemas; it requires schema-creation privileges.
For a real existing database, take a verified quiesced backup first; test a restored copy before upgrading production.
Do not stamp a schema to bypass migrations. Do not downgrade production to recover: restore a rehearsed backup.

Ollama, in its own terminal/service environment (quit a previously running desktop Ollama first if it owns the port):

```powershell
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD = '1'
ollama serve
```

These variables must be inherited by Ollama itself; putting them only in the backend `.env` is insufficient.
The cloud-disable setting is defined by [Ollama's environment configuration](https://github.com/ollama/ollama/blob/main/envconfig/config.go).
Likewise set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` and `HF_HUB_DISABLE_TELEMETRY=1` in backend service environment.
The supported guarded backend launcher sets the latter variables:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.backend.yml run --rm backend python -m scripts.release_health --dependencies-only
# Continue only when preflight passes:
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.backend.yml up -d --no-build backend
```

The Linux image does not download models or migrate at startup. Inspect preflight exit status before starting the backend.
`infra/start-backend.ps1` is a legacy native launcher, unsupported on this Smart App Control host.
For development only, plain `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` and
`npm.cmd --prefix frontend run dev -- --host 127.0.0.1` remain available; HTTP needs non-Secure cookies.
Neither Vite dev nor Vite preview is the production web server.

Create individual production users with existing password hashing, not `seed_dev_users`:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.backend.yml run --rm backend python -c "from getpass import getpass; from app.db.session import SessionLocal; from app.db.models import User; from app.core.security import hash_password; name=input('Username: '); role=input('Role (requester/reviewer/admin): '); assert role in ('requester','reviewer','admin'); password=getpass('Password: '); assert len(password)>=16; session=SessionLocal(); session.add(User(username=name,role=role,password_hash=hash_password(password))); session.commit(); session.close()"
```

Provision at least an independent requester and reviewer. Protect administrator access and user lifecycle operations.
For optional STT/TTS, use the Phase D local adapter contract, supply approved model artifacts, configure
`WORKBENCH_STT_URL`/`WORKBENCH_TTS_URL`, and verify each origin's `/health`. Disabled/unavailable speech warns
and leaves text mode. Enabled vision without an installed vision-capable model fails; disabled vision warns.
Preflight verifies BGE files but does not load Docling/PaddleOCR engines; provision their artifacts and run ingestion
acceptance before offering those features. See [Phase D](local_voice_and_language_resources.md).

For optional n8n, install a site-approved local version, disable telemetry/external nodes and keep it on a private network.
Review `infra/n8n/05-wb-operational-summary.json`; use the existing HMAC timestamp/nonce/summary contract with
`WORKBENCH_AUTOMATION_SECRET` (at least 32 random characters) and a current reviewer/admin UUID.
Earlier n8n templates are not authority to approve or perform plant writes. Start n8n only after backend readiness;
stop it during backup. No n8n container/version is newly invented by this phase.

## Release health

```powershell
$env:PYTHONPATH = "$PWD;$PWD/backend"
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.backend.yml run --rm backend python -m scripts.release_health
# Machine-readable result and the same exit status:
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.backend.yml run --rm backend python -m scripts.release_health --json
```

PASS/WARNING/FAIL cover database, migration head, Qdrant, Ollama, both models/digests/quantization, context,
vision, speech, disk, directories, retrieval artifacts, retrieval runtime, sovereignty, egress/resource policy,
secrets/config, backend `/ready` and the frontend build. Exit 1 means a blocker. `RETRIEVAL RUNTIME` loads the
local BGE embedding and reranker models (local files only, no download), embeds one fixed synthetic string and
reranks two fixed synthetic passages within 180 seconds, so a native runtime the OS refuses to load (for example a
PyTorch DLL blocked by Windows Smart App Control) fails the release instead of passing on file presence alone. Its
detail names only the failing stage and exception type. It never emits raw settings, connection strings,
exception bodies or keys. Development credentials, non-Secure cookies, HTTP CORS or a non-confidential mode correctly
fail the production check. `--dependencies-only` omits backend/frontend so it can gate backend startup.
Frontend PASS means a build exists; TLS ingress and browser functional tests are separate site acceptance.

## Backup and restore

Stop backend, all ingestion/writers, n8n and scheduled jobs. Keep PostgreSQL/Qdrant running for their backup APIs.
Quiescence is an operator assertion, not a distributed lock. Each PostgreSQL dump is transactionally consistent;
the database, Qdrant snapshots and files are **not atomic across services**. Concurrent writes invalidate the recovery
assumption. Back up to a new encrypted destination on protected storage outside data/model roots:

```powershell
$env:PYTHONPATH = "$PWD;$PWD/backend"
$Backup = Read-Host 'New absolute backup directory'
& backend/.venv/Scripts/python.exe -m scripts.backup create $Backup --quiesced --compose
& backend/.venv/Scripts/python.exe -m scripts.backup verify $Backup
```

`--compose` explicitly uses the bundled local container's backup administrator and configured database name;
omit it to use native `pg_dump` and credentials from `DATABASE_URL`. Never back up a different site's service by
assuming Compose project names. Native backup rejects URL query overrides. Partial failures leave no valid manifest.
The manifest covers PostgreSQL archive, complete local data tree and all collection snapshots, with SHA-256 per file.
Qdrant snapshots remain on its server too; rotate them using its snapshot API after off-host validation.

PostgreSQL contains users/sessions, verified knowledge and gap state, audit records, evidence manifests and durable
execution records. The file tree contains source uploads, OCR/P&ID artifacts, ingestion manifests and derived files.
Back up model weights/version manifests, secret configuration, database roles/grants, Qdrant aliases/config and
independently retained audit checkpoints separately. They are explicitly excluded from the application bundle.
Use a single-node Qdrant here; distributed shard/cluster recovery needs its own tested procedure.

### Restore rehearsal, then controlled recovery

Restore only into a new isolated database, empty file directory and isolated Qdrant service of matching versions.
Keep application writers off until every component has been verified. Never use `--clean` against production.
The following uses the bundled PostgreSQL container and a fresh name, and never drops an existing database:

```powershell
& backend/.venv/Scripts/python.exe -m scripts.backup verify $Backup
if ($LASTEXITCODE -ne 0) { throw 'Backup verification failed' }
$RestoreDb = 'workbench_restore_' + (Get-Date -Format 'yyyyMMddHHmmss')
docker compose -f infra/docker-compose.yml cp "$Backup/postgres.dump" postgres:/tmp/workbench-restore.dump
docker compose -f infra/docker-compose.yml exec -T postgres createdb -U postgres $RestoreDb
if ($LASTEXITCODE -ne 0) { throw 'Restore target must be newly created' }
docker compose -f infra/docker-compose.yml exec -T postgres pg_restore -U postgres -d $RestoreDb --exit-on-error --single-transaction --no-owner --no-acl /tmp/workbench-restore.dump
if ($LASTEXITCODE -ne 0) { throw 'Database restore failed; do not start writers' }
$RestoreData = Read-Host 'New empty local restore-data directory'
if (Test-Path -LiteralPath $RestoreData) { throw 'Choose a new target directory' }
Copy-Item -LiteralPath "$Backup/data" -Destination $RestoreData -Recurse
# Target must be an isolated Qdrant instance, never the serving production collection.
$RestoreQdrant = Read-Host 'Isolated local Qdrant base URL'
$Manifest = Get-Content -LiteralPath "$Backup/manifest.json" -Raw | ConvertFrom-Json
foreach ($Snapshot in $Manifest.qdrant) {
    $SnapshotFile = Join-Path $Backup $Snapshot.file
    curl.exe --fail --noproxy '*' -X POST "$RestoreQdrant/collections/$($Snapshot.collection)/snapshots/upload?priority=snapshot&wait=true" -F "snapshot=@$SnapshotFile"
    if ($LASTEXITCODE -ne 0) { throw 'Qdrant restore failed; do not start writers' }
}
```

Qdrant's documented [snapshot recovery](https://qdrant.tech/documentation/operations/snapshots/) supports this
collection restore; [`priority=snapshot`](https://api.qdrant.tech/api-reference/snapshots/recover-from-uploaded-snapshot)
is required when creating a collection from a snapshot. Restore aliases/config independently and allow temporary
space for snapshot plus restored collection. Copy commands preserve bytes but permissions must be reapplied.

Point a separate backend environment at the restored database/data/Qdrant. Reapply least-privilege grants and
rotate/revoke restored sessions as appropriate. Run Alembic current/check, release health, audit chain verification,
source-hash/evidence checks, a known retrieval, verified-knowledge lifecycle read and interrupted-run inspection.
Do not automatically resume every restored durable run: inspect ownership, approvals and evidence freshness first.
Compare database row counts and Qdrant collection point counts with the quiesced baseline. Record elapsed recovery
time and a successful operator-approved rehearsal before allowing production cutover. A checksum-only PASS is not
a proof of recoverability. If any step fails, keep the target isolated and retain the original backup unchanged.

## Regression CI and local validation

`.github/workflows/regression.yml` runs backend tests (including Phase 11 security and Phase E), disposable-schema
migrations with `alembic check`, frontend lint/tests/build, and hashes of all 168 frozen benchmark files.
Normal CI never calls Ollama or executes BLIND. CI uses synthetic data and disposable credentials, not production secrets.
The optional workflow-dispatch job runs only on a dedicated approved on-premise Linux runner; protect its environment
with required reviewers, preinstall dependencies/models, and never attach production files or credentials.

```powershell
$LinuxChecks = @'
set -e
git config --global --add safe.directory /source/.git
git clone --quiet --no-hardlinks /source /tmp/release-check
cd /tmp/release-check
export PYTHONPATH=/tmp/release-check:/tmp/release-check/backend:/tmp/release-check/backend/tests
export WORKBENCH_DATA_ROOT=/tmp/release-check/data
python -m scripts.frozen_integrity
python -m scripts.validate_migrations
python -m unittest test_browser_audio test_seed_guards test_release_retrieval_runtime test_local_voice test_voice_identifier_review test_advanced_c test_phase_e test_phase11_security -v
python -m unittest discover -s backend/tests -v
python -m scripts.nonblind_regression
'@
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.backend.yml run --rm -e WORKBENCH_TEST_POSTGRES=1 -e MODEL_ALLOWED_HOSTS=127.0.0.1,localhost,::1,host.docker.internal -v "${PWD}:/source:ro" backend sh -c $LinuxChecks
git diff --check
git diff --exit-code -- benchmark
```

These checks use committed source in a disposable Linux filesystem, avoiding Windows bind-mount startup latency;
commit reviewed changes before reproducing the release run. Git's ownership exception is limited to the read-only
source repository inside the disposable container. Test fixtures need loopback plus the private host bridge in their
allowlist; the running backend remains configured only for its chosen private model host.
The `nonblind_regression` command plans exactly 30 development/validation cases without inference. Live regression requires
both `WORKBENCH_LIVE_REGRESSION=1` and `python -m scripts.nonblind_regression --execute`. It reuses frozen Stage 2
schema, route/tool, citation, missing-evidence, HITL, refusal and injection scoring, with both configured models.
It writes only new timestamped files under ignored `data/regression`; every selected split is checked before inference.
It exits nonzero for any failing case (including existing baseline failures); compare per-case results with frozen
development/validation results to distinguish new regressions. Application guardrail tests remain necessary because
the model harness is read-only and does not exercise the whole authenticated application. No tuning against BLIND.

## Production controls: guarantees versus requirements

| Area | APPLICATION GUARANTEE | DEPLOYMENT REQUIREMENT |
|---|---|---|
| Inference/storage | Gateway rejects hosted endpoints/cloud model tags; configured PostgreSQL/Qdrant are local/private; local files; no plant-write tools | Trusted DNS, local mounts (a local path can conceal a network mount), protected service accounts and actual routing/firewall enforcement |
| Egress | Confidential mode blocks optional public connectors; local clients disable proxy/redirect inheritance | Deny outbound Internet at host/container/network layers, including Docker/WSL traffic; separately allow required private DNS/NTP/services; test from the service account and capture firewall evidence |
| Transport/auth | Server authorization, hashed passwords, opaque sessions, configurable Secure cookies and explicit CORS | Site TLS reverse proxy, certificates, HTTPS-only frontend/API, HSTS, rate/body limits, Secure cookie config; restrict docs/health/admin ingress |
| PostgreSQL | Migrations and transactional state/audit guards | Separate migration owner and runtime login; runtime gets only necessary SELECT/INSERT/UPDATE and sequence permissions, never superuser/DDL/trigger-disable rights; restrict sensitive DELETE and roles; private TLS where crossing hosts |
| Qdrant | Compose loopback exposure; backend local/private policy | Keep ports 6333/6334 unexposed to users/Internet; private firewall or authenticated proxy. Current backend has no Qdrant API-key setting, so do not enable API-key auth without adding compatible client configuration |
| Persistence | PostgreSQL stores audit/verified/durable state; file manifests preserve evidence links | Encrypt volumes/backups, protect audit checkpoints off-host, set explicit retention and tested recovery objectives; do not prune audit/evidence backing active approvals |
| Logs | Prompt logging defaults off; release diagnostics omit secrets | Configure OS/container log rotation, restricted readers and retention. Queries/transcripts in stored records are confidential; never ship them to hosted telemetry |
| Capacity | Bounded model context/output and HTTP timeouts | Measure RAM/VRAM/disk/concurrency; set service/container memory/CPU limits after load testing, reserve disk for snapshots and use restart monitoring |

Windows enforcement: use a dedicated service account/host, Windows Defender Firewall and the site gateway to
deny default outbound traffic, with narrowly scoped private-service exceptions. Account for Docker Desktop/WSL
virtual adapters: a Python executable rule alone does not cover containers or Ollama. Linux: equivalent nftables
or site firewall policy, systemd service isolation and container-forwarding rules. Do not apply unreviewed blanket
firewall commands remotely; stage the policy with console recovery access. Verify denial with an approved external
test destination using non-confidential probes and retain evidence. Application-level blocking is not an air-gap.

Linux notes: use `python3.11 -m venv backend/.venv`, `backend/.venv/bin/python`, `export PYTHONPATH="$PWD:$PWD/backend:$PWD/backend/tests"`,
`npm` and `curl` equivalents. Start guarded backend with `python -m scripts.release_health --dependencies-only && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
under a site-managed service unit. Build wheelhouse and native dependencies for Linux separately; do not reuse Windows wheels.

See [Government resource integration](government_resource_integration.md) and the
[Phase 11 audit](final_security_sovereignty_audit.md) for policy boundaries and earlier findings.

## Phase E validation record — 2026-09-28

| Check | Result |
|---|---|
| New deterministic Phase E acceptance | 18 passed |
| Required targeted security/routing/durability/P&ID/maintenance/enterprise/voice selection, including Phase E | 178 passed |
| Full PostgreSQL-enabled backend suite | 869 passed, 0 failed, 0 errors, 1 skipped (opt-in live-model smoke) |
| Frontend | Lint PASS, 11 tests passed, production build PASS; no frontend source changes |
| Migration | Fresh 0001–0016, 0015-to-head, repeated head upgrade and `alembic check` PASS |
| Recovery rehearsal | Isolated PostgreSQL dump/restore retained user, knowledge candidate, audit chain and interrupted execution; nested source manifest and Qdrant point restored; restored schema check PASS |
| Offline Compose | Configuration validation PASS; no pulls/deployment performed |
| Frozen benchmark | All 168 SHA-256 values match worktree and Git blob bytes; no modified benchmark files |
| Non-BLIND | Plan selects exactly 30 development/validation cases; live inference not requested or executed |
| Secret scan | 683 tracked/nonignored text files scanned, no high-confidence key/private-key candidates; no tracked/nonignored `.env`. Pattern scan is not proof of absence or a fresh history audit. |
| Diff | `git diff --check` PASS; historical migrations unchanged; no commit |

The first sandboxed full run had one existing sensor-artifact write failure outside the session's writable root.
The isolated failing test and final full suite passed with worktree filesystem access; no production behavior was
changed to hide that failure. Recovery rehearsal fixture construction was corrected before the successful run.
The rehearsal used only synthetic data and temporary databases/isolated Qdrant; those services were cleaned up.

Live release health verified PostgreSQL, migration head, Qdrant, Ollama, both required model tags with Q4_K_M,
context capacity and local configuration. The frontend build was then present. Its exit remains **1** for this
unprovisioned deployment worktree: retrieval artifacts are absent, development mode/credentials/cookies/CORS are
not production settings, and no backend is serving `/ready`. Optional vision/STT/TTS and unpinned digests warn.
These are explicit site provisioning gates, not a claim of a commissioned production deployment.
Fresh Python wheelhouse installation, disconnected end-to-end operation, TLS/firewall acceptance and live voice
quality were documented but not performed in this phase. GitHub-hosted CI was authored and its component commands
validated locally; no remote workflow run or hosted deployment was triggered. Netlify was not used.

## D-LIVE integration

The validated Windows speech option is faster-whisper 1.2.1 / Whisper small
multilingual on CPU/int8 and eSpeak NG 1.52.0, served by
`backend/scripts/local_speech_runtime.py` at `127.0.0.1:8765`.
Follow [the Phase D provisioning and validation commands](local_voice_and_language_resources.md).
Its Python 3.11 speech venv is independent of the backend venv. Provision its
packages and models before disconnecting; preserve artifact hashes and capture
its wheels for that interpreter. No startup download or hosted fallback exists.

Keep `WORKBENCH_STT_URL=http://127.0.0.1:8765/stt` and
`WORKBENCH_TTS_URL=http://127.0.0.1:8765/tts` when merging the offline overlay into
an already provisioned site. Start speech before dependency preflight. STT/TTS
report PASS for a healthy local origin, WARNING when unconfigured, and a distinct
WARNING when configured but unavailable. Text fallback remains available in both
warning cases. Health is availability, not recognition accuracy: Hindi/Tamil
synthetic recognition remains poor. Damaged identifiers require human review;
raw transcripts are never silently corrected. Confidential speech remains
restricted to LOCAL_APPROVED resources.


## Linux runtime release requirements (M1 / H1 / M2 / H2 / M3)

Windows Smart App Control remains enabled and unchanged. Do not run native Windows Torch or disable code integrity.
The Dockerfile includes `libgl1`, `libglib2.0-0` and `libgomp1` for OpenCV/Paddle/native imports and eSpeak NG for local TTS.
Its base image is digest-pinned; apt repositories may change, so preserve the built image digest and signed archive for
byte-identical offline deployment. The Python lock pins versions, not wheel hashes; hash the approved wheelhouse/archive
in the signed release manifest. Do not claim a fresh online image build is byte-identical.

Set `BACKEND_DATABASE_URL` in protected root `.env` to the intended account with `postgres` as hostname and URL-encoded
credentials. This is deliberately required; it must agree with the provisioned database, without printing the URL.
Models mount read-only and data stays on this machine. Backend port 8000 is published only on `127.0.0.1`; existing DB and
Qdrant ports remain loopback-only. The backend runs as UID 10001; Linux bind directories must grant that user access.
Container model traffic uses `host.docker.internal:11434`, explicitly allowed and checked for private resolution.
First test host Ollama access through Docker Desktop's private host bridge with Ollama still bound to loopback. If that
host configuration cannot reach loopback, provision a host bridge-only listener/firewall rule; never bind Ollama publicly
or disable the firewall. Keep `OLLAMA_NO_CLOUD=1` on the Ollama process. No cloud fallback exists.

```powershell
$ComposeBackend = @('--env-file', '.env', '-f', 'infra/docker-compose.yml', '-f', 'infra/docker-compose.backend.yml')
docker compose @ComposeBackend build backend
docker compose @ComposeBackend up -d postgres qdrant
# Use reviewed migration-owner credentials for migrations, then the restricted runtime account.
docker compose @ComposeBackend run --rm backend python -m alembic -c backend/alembic.ini upgrade head
docker compose @ComposeBackend run --rm backend python -m alembic -c backend/alembic.ini current
docker compose @ComposeBackend up -d --no-build backend
# After loading approved image archives on a disconnected host:
docker compose @ComposeBackend -f infra/docker-compose.offline.yml up -d --no-build --pull never
```

For a wheelhouse instead of an image transfer, on connected Linux x86_64/Python 3.11 run
`python -m pip wheel -r backend/requirements-linux.lock --wheel-dir wheelhouse`.
Include every transitive wheel (including official `+cpu` Torch/torchvision); sign and verify file hashes.
Rehearse installation with `python -m pip install --no-index --find-links wheelhouse -r backend/requirements-linux.lock`
and `python -m pip check` on clean Linux. Windows wheels are unusable here. The image archive is the simpler supported
offline path and also captures native libraries; a wheelhouse alone does not include libGL or eSpeak.

Optional speech uses the same image and backend network namespace, so the adapter stays on loopback with no published
speech port. Provision `models/local-speech/faster-whisper-small` first and set `WORKBENCH_STT_URL=http://127.0.0.1:8765/stt`
and `WORKBENCH_TTS_URL=http://127.0.0.1:8765/tts` in `.env`, then:
`docker compose @ComposeBackend --profile speech up -d --no-build backend speech`.
PyAV decodes WebM/Opus, Ogg/Opus, MP4/AAC and WAV in memory to mono 16 kHz samples. MP4 depends on the bundled codec;
unsupported containers/codecs return 415 (`unsupported_audio_format`), invalid input/duration returns 422 (`invalid_audio`),
and outages retain `runtime_unavailable`. Input remains limited to 4 MiB and 60 decoded seconds, including compressed input.
Decode happens under the existing single-request lock, containers close on every path, external media protocols are disabled,
and no raw audio or conversion subprocess is written to disk. Browser-origin and non-loopback requests remain rejected.

Both known-password seed scripts refuse before side effects unless `WORKBENCH_DEPLOYMENT_MODE=development`.
Confidential/public deployments are refused; invalid production mode configuration also fails closed. There is no override.
Use individually provisioned accounts with existing RBAC in production.

**FIRST REQUIRED PHASE F FRONTEND ITEM:** H3 ? identifier review UI must handle `identifier_review` and
`technical_identifiers` and require human review. This backend task deliberately does not implement H3.

Backup management commands retain the existing host-side Python 3.11 tool environment and Docker CLI;
they invoke PostgreSQL 17 tools in the existing database container and do not import Torch.
The backend image intentionally has neither Docker socket access nor host backup privileges.

### Pre-frontend blocker validation — 2026-09-28

- M1 was already committed as `e47d46b` (exactly the four release-health files); reviewed and preserved.
- Clean Linux image build and `pip check` passed: Python 3.11.16, Torch 2.14.0+cpu (CUDA absent), PyAV 18.1.0;
  all 178 installed package versions match the release lock. Git is included for existing frozen-asset checks.
- Targeted browser audio, seed guards, release health, Phase D/D-LIVE, Phase E and Phase 11 security: 87 passed.
- Full backend in a temporary Linux checkout with PostgreSQL: **890 passed, 0 failed, 0 errors, 1 skipped**
  (the opt-in live-model query). The first Windows bind-mount attempt exposed missing Git, a fixture allowlist
  mismatch and a startup timeout; the final image and documented Linux checkout procedure resolved those errors.
- Running Compose backend `/health` and `/ready` passed, including PostgreSQL, Qdrant and host-local Ollama.
  Database and code migration heads both equal `0016_enterprise_knowledge`.
- Real local retrieval probe: one 768-dimensional embedding and two reranked synthetic passages passed in 19.3 seconds.
- Real in-memory eSpeak → WebM/Opus, Ogg/Opus, MP4/AAC and WAV → Whisper round trips all passed.
  Speech has no published port; backend, PostgreSQL and Qdrant are published only on host loopback.
- Frontend lint, 11/11 tests and build passed; frontend source unchanged.
- Frozen benchmark: all 168 committed files match the manifest. The pre-existing local edit to
  `benchmark/reports/final_model_runtime_readiness.json` remains untouched and is not part of the frozen release;
  the final suite used committed benchmark bytes in its isolated checkout. BLIND was not executed.
- Windows Smart App Control remained enabled (`VerifiedAndReputablePolicyState=1`); no Windows security changes.
- H3 remains the **FIRST REQUIRED PHASE F FRONTEND ITEM**. No frontend implementation or push was performed.
