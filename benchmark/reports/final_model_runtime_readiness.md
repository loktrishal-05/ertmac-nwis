# Final model comparison ? Stage 1 readiness

**FINAL MODEL COMPARISON STAGE 1 BLOCKED**

Timestamp: 2026-09-27T04:09:00.263502+00:00 (UTC; local zone Asia/Calcutta). HEAD: `6dba5c11d1cc6e0479413b8c860b4167ca4c25aa`, branch `master`.

Runtime and deployment checks are complete. The exact Stage 2 preflight discovered one frozen evidence-binding defect: **REF-005**. Do not run Stage 2 until it is resolved under explicit authorization. No final winner was selected.

## Frozen benchmark

75 cases: 15 DEV, 15 VALIDATION, 45 BLIND; 15 categories. All 101 pre-existing benchmark files are byte-identical to Phase 10.3 (`39e6d16`). Case SHA-256:

`8bbb958865e0042a6951c05342b4cb67e4791e0515f32b2831607b408c9176bb`

The JSON companion records all 101 current hashes for execution preflight. No benchmark inference, validation inference, or blind inference ran. The case/split/mapping inspections were deterministic file validation only. New readiness reports do not change frozen inputs or previous results.

## Ollama and inventory

CLI and server: **0.34.4**. Only `qwen3.5:9b` installed; no 4B, 35B-A3B or equivalent tag appears in local `/api/tags` / `ollama list`.

- Exact tag: `qwen3.5:9b`
- Digest: `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`
- Disk size: 6,594,474,711 bytes (6.6 GB decimal)
- Parameters: 9.7B; GGUF `qwen35`, Q4_K_M
- Advertised model context: 262144; actual loaded/tested context: **16384**
- Capabilities reported: completion, vision, tools, thinking
- Runtime defaults: presence penalty 1.5, top-k 20, top-p 0.95; health/Stage 2 explicitly override temperature to zero and seed to 42.

## One non-benchmark health request

One POST to `http://127.0.0.1:11434/api/chat`, no retries. Synthetic request asked for `{"healthy":true,"value":2}`, unrelated to project or benchmark truth. Prompt-only JSON request, no native format override; stream=false, think=false, temperature=0, seed=42, context=16384, output cap=64, timeout=180 seconds.

**PASS**, HTTP 200, valid exact JSON, done_reason=stop. Elapsed **46.003 seconds**, including **41.476 seconds load**, 1.421 seconds prompt evaluation and 2.858 seconds output evaluation. 44 prompt tokens and 10 output tokens. This tiny cold-start call is not benchmark throughput or quality evidence. Exact request/native response are in the JSON companion.

## Hardware

- Windows 11 Home Single Language; Intel Core i5-12450H, 8 cores / 12 logical processors.
- Usable RAM: **15.70 GiB** (16,457,592 KiB); initial free 4.41 GiB; about **1.14 GiB free** with services and model loaded. These are time-varying snapshots.
- NVIDIA RTX 2050: **4096 MiB VRAM**, driver 536.52, nvidia-smi CUDA capability 12.2; Intel UHD also present.
- Initial GPU free snapshot: 3918 MiB. Loaded Ollama allocation: 1,720,367,184 bytes VRAM; placement **74% CPU / 26% GPU**.
- C: free **240.38 GB decimal / 223.87 GiB** at initial measurement.

No system settings changed. No throughput extrapolation from advertised hardware.

## Services and schema

Docker Desktop was stopped; launched installed Docker Desktop hidden. Existing containers were stopped. Ran:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml up -d --no-recreate --pull never postgres qdrant
```

Existing containers and named volumes retained; no pulls, resets, volume deletion or recreation. Docker Engine 29.6.2. PostgreSQL container healthy, loopback 5432; Qdrant running, loopback 6333/6334.

Backend connection **SELECT 1 PASS**, PostgreSQL **17.11**. Initial public-schema revision was `0010_phase5f_repairs`. Inspected committed upgrade functions 0011?0014: they add tables/indexes and widen CHECK constraints; no deletion of data/tables in upgrade path. Applied the documented normal procedure from `backend/`:

```powershell
.venv/Scripts/python.exe -B -m alembic upgrade head
.venv/Scripts/python.exe -B -m alembic current
.venv/Scripts/python.exe -B -m alembic check
```

Now **0014_product_integration (head)**. `alembic check`: **No new upgrade operations detected**. Verified `verified_knowledge`, `knowledge_packs`, `operator_notes`, `automation_receipts` exist.

Qdrant `/readyz`: **200, all shards are ready**. Existing collections: `knowledge_chunks_v1_hybrid_v1`, `knowledge_chunks_v1_dense_backup`.

Application readiness functions, invoked directly with real configured dependencies, report ready. This is not a claim that an HTTP FastAPI server was started or checked; its `fastapi=true` field is intrinsic to the function. Benchmark adapters use frozen corpus files, not live PostgreSQL/Qdrant lookups; service deployment checks are separate.

## Sovereignty

Local Ollama, PostgreSQL and Qdrant; data/model paths local. Application proof: sovereign, local_only, hosted_ai_configured=false, cloud_ai_enabled=false; STT/TTS disabled. The synthetic request used loopback HTTP with environment proxies/redirects disabled. Stage 2 sets local Ollama explicitly; uses the existing gateway locality checks and disables hosted tracing in its command.

No confidential/project benchmark contents were sent to hosted models. Public catalog lookup involved model names only. Zero gateway counters in the separate proof process do not count the one direct synthetic HTTP request. No firewall/physical network isolation is claimed.

## Candidates

| Candidate | Installed | Runnable | Resource status | Stage 2 today |
|---|---|---|---|---|
| qwen3.5:9b | Yes | Health PASS | RESOURCE_RISK | Runtime eligible; execution blocked by REF-005 |
| qwen3.5:4b | No | Untested | NOT_INSTALLED | Requires authorized provisioning and one health check, plus REF-005 resolution |
| qwen3.5:35b (35B-A3B family) | No | Untested | NOT_PRACTICAL_ON_CURRENT_MACHINE | Exclude today |

The minimum additional practical candidate is **4B**. Official [4B catalog](https://ollama.com/library/qwen3.5:4b) lists Q4_K_M, 3.4 GB (catalog digest prefix 2a654d98e6fb). Full GPU fit is not guaranteed once context/runtime overhead is included. Provisioning was not performed.

The official [35B catalog](https://ollama.com/library/qwen3.5:35b) confirms tag `qwen3.5:35b`, qwen35moe, Q4_K_M, 24 GB (catalog digest prefix 3460ffeede54). Its package exceeds this machine's combined RAM/VRAM before overhead; impractical for today's deadline is a resource-based assessment, not a failed live load claim.

## Stage 2 blocker

The zero-inference preflight resolves **29/30** selected DEV+VALIDATION cases. `REF-005` has `SENSOR-P204-A` with `window_bindings=[]` and `window_binding_status=family_resolved_specific_window_unspecified` in the frozen mapping. `assets.py` requires an assigned bounded sensor window; `evaluate.py:resolve()` raises **No source-assigned bounded sensor window**.

Do not guess a window, discard REF-005, substitute evidence, weaken the loader, or treat this as a model failure. Review the authoritative assignment and explicitly authorize/version any necessary freeze correction before changing it. The first interpreter preflight attempt was interrupted before evaluation; subsequent deterministic inspection confirmed this blocker. No model requests occurred during preflight.

Only one model is installed. That independently prevents a completed multi-model comparison; it does not by itself make runtime readiness fail.

## Exact prepared Stage 2 command ? DO NOT RUN YET

The frozen CLI hard-codes DEV, 9B and old result filenames; do not invoke its main function for comparison. The JSON companion embeds a syntax-checked orchestration source in `stage2.runner_source`. It reuses unchanged `load_cases`, `load_mapping`, `resolve`, `evaluate`, and `persist`. Model label is corrected after evaluation only, because the frozen function hard-codes the top-level result label; prompts/scoring remain unchanged.

```powershell
Set-Location 'C:\Users\Lohith k\Desktop\sovereign-agentic-workbench'
$env:PYTHONPATH='backend'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:LANGCHAIN_TRACING_V2='false'
$env:LANGSMITH_TRACING='false'
backend/.venv/Scripts/python.exe -B -c "import json; from pathlib import Path; r=json.loads(Path('benchmark/reports/final_model_runtime_readiness.json').read_text(encoding='utf-8')); exec(compile(r['stage2']['runner_source'], '<stage2-plan>', 'exec'))" qwen3.5:9b
```

For the 4B candidate, only after authorized provisioning and readiness, use the identical command with final argument `qwen3.5:4b`. No automatic download is embedded.

For **zero-inference preflight only**, append `--check`. It currently exits BLOCKED at REF-005 before output creation or inference. An authorized future freeze correction requires updating the hash baseline and rerunning preflight; do not bypass the guard.

Execution configuration: DEV then VALIDATION, exactly 30 unique IDs, no blind IDs; temperature 0, seed 42, context 16384, output 1536, think=false, 900-second call limit, no retries or repair calls, one attempt per case. At most 60 model calls per candidate. Candidates run serially. Process-scoped sleep prevention is held during execution and released afterward, without changing system power settings.

Separate exclusive output directories:

- `benchmark/results/final_model_stage2_qwen3_5_9b/`
- `benchmark/results/final_model_stage2_qwen3_5_4b/`

Each contains `results.jsonl`, `results.csv`, `report.md`. Existing directories block repetition; STARTED/NOT_RUN records preserve interrupted execution for review. Failures remain failures; REVIEW_REQUIRED is not an overall semantic PASS. No Stage 2 directories were created in Stage 1.

Historical 9B data: 1989.868 seconds for 15 DEV cases, approximately **66.3 minutes for 30** by linear extrapolation. Reserve **90?120 minutes** as planning allowance, not a measured prediction. 4B timing is unknown. Runtime update and current memory pressure can change timing. Worst-case 60 calls at 900 seconds is 15 hours; no deadline guarantee. Provisioning and manual semantic review are additional.

## Validation and scope

No application code/configuration or frozen benchmark files changed. Full backend tests not rerun. Migration status and drift checks passed. Runner syntax checked; selected-case preflight correctly blocked. Final Git whitespace/frozen-hash verification is recorded in the JSON companion. Readiness reports are the only repository files created by this task; previous tooling changes retained.

**FINAL MODEL COMPARISON STAGE 1 BLOCKED**

Next action: resolve the frozen REF-005 binding under explicit authorization, then rerun zero-inference preflight; provision/health-check 4B only when authorized. Stage 2 and BLIND remain unexecuted. No commit.
