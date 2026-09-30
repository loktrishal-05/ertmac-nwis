# C2 backend judge demo runbook

C2 starts from frozen B2 `70f90606346e81c4c36f916be967a2d4cecc541a`. No API, risk, eligibility, alert, migration, or seed behavior changes. All demo domain records are `synthetic_demo`; none are Oil India records. Use this runbook for C2 instead of the older B1 startup instructions in README.md.

## Prerequisites and isolated startup (PowerShell)

- Work from `C:\Users\Lohith k\Desktop\ertmac-nwis-backend-c2`, branch `pivot/nwis-backend-c2`.
- Docker Desktop with Linux containers and Compose supporting `!override` (2.24.4+).
- Existing local `bge-base-en-v1.5` and `bge-reranker-base` directories, each with config/tokenizer/weights. They are mounted read-only; no hosted embeddings or automatic downloads.
- Host Ollama reachable from Docker at `host.docker.internal:11434`, with `qwen3.5:9b` installed. `/ready` checks presence, not inference. NWIS uses deterministic advisory templates and does not require Qwen inference.
- Port 8012 free. B2 remains on 8011. The C2 override uses its own project/network/PostGIS/Qdrant volumes. Never omit the override or point these scripts at a shared database.

```powershell
Set-Location 'C:\Users\Lohith k\Desktop\ertmac-nwis-backend-c2'
$env:NWIS_MODEL_DIR='C:/Users/Lohith k/Desktop/sovereign-agentic-workbench/models'
$c2=@('-f','infra/docker-compose.nwis.yml','-f','infra/docker-compose.nwis-c2.yml')
docker compose @c2 config --services
docker compose @c2 up -d --wait postgres qdrant
docker compose @c2 run --rm --no-deps backend python -m alembic -c backend/alembic.ini upgrade head
docker compose @c2 run --rm --no-deps backend python -m scripts.seed_nwis --index
docker compose @c2 up -d backend
Invoke-RestMethod http://127.0.0.1:8012/ready
```

Check each command succeeds before proceeding. The validated machine already has the dependency image `ertmac-nwis-backend:local`; C2 mounts its own source tree over `/workspace`. On a machine without that image, build it with the existing Dockerfile (`docker compose @c2 build backend`) before startup. No dependency or base image changes were needed for C2. Do not rebuild the shared image tag while another integration process is rebuilding it.

The default database password belongs only to the loopback-bound isolated synthetic stack; it is not an application/admin credential. Set `NWIS_DB_PASSWORD` before first database creation if needed. Changing it after a volume exists does not rotate PostgreSQL credentials. Google, SMTP, and public signup are disabled by the C2 runtime configuration.

## Limited demo reviewer

```powershell
docker compose @c2 exec backend python -m scripts.provision_nwis_demo
```

Enter a unique password of 16..128 characters at the hidden prompt. Default username: `nwis_demo_reviewer`. Optional alternative: `docker compose @c2 exec -e NWIS_DEMO_USER=judge_reviewer backend python -m scripts.provision_nwis_demo`.

The command creates only a reviewer, using the existing Argon2/session authentication. It requires development mode and the dedicated `nwis` database. Repeating with the same account/password is idempotent; a different password, role, disabled state, or pending account fails without overwriting it. No admin is created, no fixed password is shipped, and no credentials are printed. Password recovery/rotation remains with the existing account-management mechanism; this script is not a password-reset backdoor.

Login via `POST /auth/login` with username/password, retain the session cookie, read `/api/terms`, then POST `{"version":"nwis-advisory-v1","accepted":true}` to `/api/terms/accept`. Browser requests must include credentials and pass the frozen Origin/Referer check (existing localhost:5173 frontend origin). The reviewer can view/search/query/assess, replay, review advisories, validate eligible events, and read its own audit. It cannot ingest reports, read restricted wells, or read other actors' audit. Event validation is a separate explicit human action; the golden smoke never promotes its source events.

Validation used `nwis_c2_validation`, a reviewer with a randomly generated password held privately in the container, not a shared team credential. Provision your own account using the command above. Use a fresh rehearsal project for that account's first full review demonstration if the validation advisory has already been acknowledged.

## Canonical numerical scenario

The complete machine-readable fixture is [golden_demo_fixture.json](golden_demo_fixture.json). These are real PostGIS/B2 results, not SQLite distance estimates. Golden state: `ACTIVE-01`, field `SYNTHETIC-ASSAM-DEMO`, MD/TVD **2450 m**, formation **TIPAM_A**, as-of **2026-09-29T16:00:00Z**, radius **10 km**, look-ahead **100 m** ending at **2550 m**. TVDSS is unavailable.

| Offset | Overall rank | Distance m | Geographic | Formation | Depth | Trajectory | Program | Quality | Total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OFF-04 | 1 | 1547.28780373 | 0.7338449145684278 | 1 | 1 | 1 | 1 | .95 | 0.9550767371852642 |
| OFF-02 | 2 | 773.64911852 | 0.8566465918240312 | 1 | 1 | 0.7444444444444445 | 1 | .95 | 0.9351636554402715 |
| OFF-03 | 3 | 1160.46976544 | 0.7928716270694119 | 1 | 1 | 0.7444444444444445 | 1 | .95 | 0.9255974107270786 |
| OFF-09 | 4 | 3481.33885590 | 0.49844213668101994 | 1 | 1 | 1 | 1 | .95 | 0.919766320502153 |
| OFF-01 | 11 (closest) | 148.52676803 | 0.9707315139550204 | 0 | null | 1 | 1 | .195 | 0.41510972709325317 |

OFF-01 lacks a single matching TIPAM_A interval and usable matched depth overlap. OFF-04/OFF-09 have formation match, full 100 m TVD overlap, and higher data quality. Their evidence relevance outweighs distance. OFF-09 is a highlighted evidence analog, **not the second-ranked result**. Weight order geographic/formation/depth/trajectory/program/quality is .15/.30/.20/.15/.10/.10.

### Exact stuck-pipe risk at 100 m

- Probability: **0.7455033407089751**; confidence: **0.855**; trend: `rising`.
- Historical exposure: **0.7005921655399706**.
- `live_anomaly_contribution`: **0.15**, from persistent torque deviation. This is a bounded modifier, not +15 percentage points: `exposure + (1-exposure)*0.15` gives an actual uplift of **0.0449111751690045**.
- Supporting offsets: **OFF-03, OFF-04, OFF-05, OFF-06, OFF-09, OFF-10, OFF-11**; ten usable analogs overall.
- Top factors: `formation_match`, `historical_event_prevalence`, `torque_persistent_deviation`.
- `calibrated=false`, `advisory_only=true`. These are synthetic heuristic values, not calibrated field-event probabilities.
- Torque features: count 31, mean 13.246670967741935, std 2.177122716649357, robust_z 11.934344209025674, persistence 3. Torque contributes to stuck_pipe/torque_drag; flow to mud_loss; standpipe_pressure to kick_or_overpressure. The latter two modifiers are 0 at this timestamp. Hookload is sampled but is not mapped to a hazard modifier in B2.
- All ten telemetry channels are fresh relative to replay `2026-09-29T16:00:00Z`, **not wall-clock live data**. Freshness cutoff is 300 seconds. A query ending at 16:06 makes torque stale. Channels: MD, RPM, ROP, WOB, bit_depth, flow, hookload, mud_weight, standpipe_pressure, torque.

### Complete supporting event → report → page chain

All below are `stuck_pipe`, `TIPAM_A`, confidence .9, state `unverified`, origin `synthetic_demo`. Exact end depths, snapshot hashes, and source URLs are in the JSON fixture. Some synthetic report IDs end in `-DDR` even when the stored report type is WCR; retain the existing IDs.

| Event ID | Well/report | Page | Start MD m | TVD m |
| --- | --- | --- | --- | --- |
| EVT-e1c784feb63c30bb04cc572ea301ef3d | OFF-04 / OFF-04-DDR | 2 | 2470 | 2470 |
| EVT-00b7d3f0d01482cb574dc230e1972ddc | OFF-04 / OFF-04-DDR | 5 | 2506 | 2506 |
| EVT-5a64979d859680128efeb3986e4bc101 | OFF-04 / OFF-04-DDR | 3 | 2510 | 2510 |
| EVT-799cd22898647a9a4b719b03ba4a0df7 | OFF-03 / OFF-03-DDR | 6 | 2750 | 2530 |
| EVT-59c023472ea69bf99c56a4c75bf700ee | OFF-09 / OFF-09-DDR | 2 | 2470 | 2470 |
| EVT-aa50bf2952b33d1ce0f71cabd119e400 | OFF-09 / OFF-09-DDR | 3 | 2510 | 2510 |
| EVT-699933a0df482a63db073470b1d0e945 | OFF-05 / OFF-05-DDR | 4 | 2697.83 | 2482 |
| EVT-cfb47d22f1fafc1d0e1b3d1a540fb3c2 | OFF-06 / OFF-06-DDR | 3 | 2671.74 | 2458 |
| EVT-feb448a90730db9dcddc5557a7916831 | OFF-10 / OFF-10-DDR | 6 | 2750 | 2530 |
| EVT-60e76c41431a7f5b084b350c36d90efc | OFF-11 / OFF-11-DDR | 5 | 2723.91 | 2506 |

For example: ACTIVE-01 → OFF-04 → EVT-e1c784feb63c30bb04cc572ea301ef3d → OFF-04-DDR → `/api/reports/OFF-04-DDR/source#page=2` → stuck-pipe assessment → advisory → acknowledged review → own `advisory_review` audit entry. Always use the assessment/advisory IDs returned by the API; IDs bind the full assessment context. Do not derive them client-side.

## Judge sequence and HTTP smoke

1. Login and accept terms. View active well, nearby ranking, correlation (`lookahead_m=100`), historical events, risk, and telemetry.
2. Replay **15:58**, **15:59**, **16:00** on 2026-09-29 UTC, POSTing `/api/wells/ACTIVE-01/assess?lookahead_m=100` after each. MD advances 2449.8 → 2449.9 → 2450.
3. Fresh state emits **0, 0, 2** advisories (mud loss and stuck pipe). Same/older timestamps do not advance persistence; repeated assessment emits none.
4. Open the stuck-pipe assessment and its source links. Compare current event state against `event_at_assessment` and current/assessment hashes.
5. Query `show stuck-pipe incidents in Tipam between 2400-2700 m TVD` with `mode=nwis_evidence`, a fresh request UUID, and `retrieval=hybrid`. Query `OFF-04 TIPAM_A stuck_pipe 2470 m` with `formation=TIPAM_A,offset_limit=1` for exact identifier retrieval. The offset limit explicitly constrains the latter to the best analog; free text alone is not a well filter.
6. Acknowledge the advisory with a reason, then view own audit. Acknowledgement does not validate source events or control a rig.

```powershell
docker compose @c2 exec backend python -m scripts.smoke_nwis_demo --hybrid
```

Enter the same demo-reviewer password. Alternative username: add `-e NWIS_DEMO_USER=judge_reviewer` to `exec`. Default result: `data/nwis_c2_smoke.json` (ignored by Git). Without `--hybrid`, query retrieval is structured. Both modes still require `/ready` to be 200. The script validates response models, golden values, PDFs/hashes, review identity/time, audit, errors, and three warm latency samples per endpoint. It uses actual TCP HTTP, cookie login, real PostgreSQL and (with the flag) local BGE/Qdrant; no dependency overrides.

The smoke is repeatable with the **same reviewer** on its existing reviewed advisory. It preserves history, checks duplicate assessment/review behavior, and requires any existing acknowledgement to belong to that reviewer. Do not call assess at 16:00 before a first-run three-timestamp demonstration: B2 deliberately ignores older assessment timestamps afterward. Use a fresh rehearsal project if you already did that.

## Frozen evidence eligibility and errors

| Case | Expected, tested behavior |
| --- | --- |
| `rejected` or `review_needed`, even confidence .9 | Excluded from risk |
| Confidence .499, even `validated` | Excluded from risk |
| `unverified` with confidence .5 or higher and matching eligibility | May contribute; state remains visible |
| Later rejection/validation | Current event changes; prior assessment snapshot stays as used |
| Human validation | Explicit reviewer action, identity/time/reason audited; never silently inferred |
| lookahead 75 on risk/correlation/assess | 422 |
| Unsupported query mode | 422 |
| Unknown well | 404 with bounded detail |
| No evidence | 200 with empty evidence and insufficient-evidence answer |
| No usable analogs | 200 with null probabilities |
| Missing TVDSS / missing active MD | Empty depth-filter results / null depths and probabilities; no fabricated datum |
| Stale telemetry | `state=stale`; stale contributing channel cannot borrow freshness from sibling channels |
| Unauthenticated review / requester review | 401 / 403 |
| Duplicate review | 409 |
| Reviewer attempts report ingestion | 403 |

Alert policy remains trigger **>=.6**, confidence **>=.5**, at least two supporting wells, **three** eligible assessments, clear **<.4**, cooldown **30 minutes**, same/older timestamp dedupe, gap >5 minutes resets persistence, well/hazard/100 m MD bucket identity. B2 tests verify .5 hysteresis, .3 clearing, suppressed cooldown retries, and re-alert at minute 32 (30 minutes after the first alert at minute 2). C2 additionally tests a transient high/low condition resetting persistence.

## Runtime, PostGIS, retrieval and regression commands

```powershell
docker compose @c2 exec -T backend python -m scripts.validate_nwis_runtime
docker compose @c2 exec -T backend python -m alembic -c backend/alembic.ini check
docker compose @c2 exec -T -e NWIS_TEST_POSTGRES=1 backend python -m unittest test_nwis test_nwis_b2 test_nwis_c2 test_nwis_postgres test_nwis_retrieval -v
docker compose @c2 exec -T -e NWIS_TEST_RETRIEVAL=1 backend python -m unittest test_nwis_retrieval.RealRetrievalTests -v
docker compose @c2 exec -T backend python -m unittest test_phase5b.AuthHTTPTests test_phase_f_auth -v
```

`validate_nwis_runtime` records the exact ST_DWithin/ST_Distance SQL, parameters, distance order, and GiST query plan in `data/nwis_c2_runtime.json`. It repeats seeding twice, verifies counts/origins and all 11 report hashes, checks the audit chain, collection count and local artifacts. Repeated seed preserves modified records and adds an audit record; it is idempotent for domain rows, not audit length. These commands use real PostGIS for spatial checks; isolated SQLite is used only for non-spatial unit fixtures. PostGIS tests create/drop only their own randomly named validation database.

No benchmark command is needed for C2; the eight blind cases remain held out.

## Safe replay/reset and shutdown

Normal reseed (preserves accounts, reviews, assessments and audit):

```powershell
docker compose @c2 exec -T backend python -m scripts.seed_nwis --index
```

For a fresh alert/review demonstration, preserve old volumes and use a new named project. Stop only this C2 stack first to free port 8012:

```powershell
docker compose @c2 down
$c2=@('-p',('ertmac-nwis-c2-rehearsal-'+(Get-Date -Format 'yyyyMMddHHmmss')),'-f','infra/docker-compose.nwis.yml','-f','infra/docker-compose.nwis-c2.yml')
docker compose @c2 up -d --wait postgres qdrant
docker compose @c2 run --rm --no-deps backend python -m alembic -c backend/alembic.ini upgrade head
docker compose @c2 run --rm --no-deps backend python -m scripts.seed_nwis --index
docker compose @c2 up -d backend
docker compose @c2 exec backend python -m scripts.provision_nwis_demo
```

Record that project name to resume it. Each project gets independent database/Qdrant volumes; immutable content-addressed synthetic PDFs may be reused from this C2 worktree. No table truncation, volume deletion, audit rewriting, or destructive Git operation is required. Shutdown with `docker compose @c2 down` (no `-v`); data volumes and source files remain.

## Common failures and local performance

| Symptom | Check/fix |
| --- | --- |
| `/ready` 503, model=false | Start host Ollama; verify installed `qwen3.5:9b` and Docker access to host port 11434. NWIS templates can work while readiness is degraded, but the strict smoke must fail. |
| Missing BGE / hybrid 503 | Check `NWIS_MODEL_DIR` and both model folders; reindex with the existing seed `--index`; retry the same failed query UUID only with identical context. |
| Postgres false / migration failure | Wait for DB health, check project selection/credentials, run migration upgrade. Do not point at B2 to make the check pass. |
| Port 8012 occupied | Stop the previous C2 project using its exact name; leave B2 and other services alone. |
| Cookie login works but API 403 | Accept NWIS terms; check user role and browser Origin. Never disable RBAC/CSRF. |
| Source 404 or hash mismatch 409 | Reseed missing immutable source PDFs; investigate corrupted files instead of changing stored hashes. |
| No new advisory on repeat | Expected dedupe; use existing review or fresh rehearsal project as above. |
| Provision refuses existing account | Use the correct existing password or an unused demo username; no automatic role/password replacement. |
| Missing model in structured mode | Structured retrieval needs no embeddings, but `/ready` still requires configured runtime/model presence; label any degraded operation explicitly. |

First measured three-sample warm medians (local Docker TCP, CPU BGE, two OpenMP/MKL threads): wells **24.43 ms**, nearby **403.44 ms**, correlation **286.27 ms**, risk **557.81 ms**, assessment **97.58 ms**, telemetry **123.11 ms**, hybrid knowledge query **6999.01 ms**. These are representative local timings, not an SLA or formal benchmark. Hybrid retrieval is the visible demo wait: warm it before judges and show loading state. Structured mode is available by the frozen contract. No scoring/retrieval algorithm was optimized or changed.

Local validation results and counts are recorded in [c2_validation.md](c2_validation.md). Frontend integration should use this runbook, the JSON fixture, and the unchanged [B2 API contract](backend_api_contract.md).
