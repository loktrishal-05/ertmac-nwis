# Phase 4A — Validation

## Deterministic backend tests

```powershell
# backend/
.\.venv\Scripts\python.exe -m compileall -q app alembic scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pip check
```

Result: **110/110 tests pass** — the prior **71** Phase 0–3C tests, confirmed
unchanged, plus **39** new Phase 4A tests in `tests/test_model_gateway.py`
(38 for the gateway itself, plus one added mid-phase for the `think`
parameter — see "Mid-phase addition" below). `alembic check` reports no
drift (Phase 4A adds no migration; head remains `0003_structured_data`).
`pip check` reports no broken requirements.

New tests use `httpx.MockTransport` (built into httpx; no new test
dependency) and a real `Settings`/`ModelGateway`/`OllamaRuntime` object graph
with a fake transport — no live model, no network call, in any unit test:

- **Configuration** — allowed host accepted; public host rejected; all ten
  denylisted hosted-provider hosts rejected even when explicitly allowlisted
  (proving the two controls are genuinely independent); unknown
  `MODEL_RUNTIME` rejected; empty `MODEL_NAME` fails with `ollama list` named
  in the message; `model`/`base_url`/`runtime`/`api_key`/`endpoint` all
  rejected by `extra="forbid"` on `ChatMessage` and `ToolSpec`.
- **Source guards** — every `model_gateway/*.py` file except `registry.py`
  (which *is* the denylist) is scanned for a hosted-provider hostname; a
  separate test confirms `registry.py` still lists every one of them (so the
  denylist itself can't silently go empty); `gateway.py` and `base.py` are
  scanned, with word-boundary matching, for Ollama-specific wire-protocol
  tokens — matching exactly (not substring) so "formatting" in a docstring
  can't trip a false positive on "format".
- **Request construction** — `options` carries temperature 0, the configured
  seed, `num_ctx`, `num_predict`; `stream` is always `false`; `format` is
  present only when a schema was supplied; **`think` is sent when explicitly
  set (`True`/`False`) and omitted entirely when `None`.**
- **Structured output** — valid first pass (`repair_attempts == 0`); invalid
  → one repair → valid (`repair_attempts == 1`, and the repair message
  contains only the validator's error text, never the expected value);
  invalid twice → `StructuredOutputError` with raw text and validation
  errors preserved; fenced ` ```json ` stripped; trailing prose around a
  valid JSON object is a failure, not something salvaged; nested `$defs`/`$ref`
  inlined correctly and exercised end to end through a two-level schema.
- **Tool calls** — a well-formed call is parsed; a name outside the supplied
  specs raises `ToolCallProtocolError`; unparseable arguments raise the same;
  `generate_with_tools` has no `execute_tool`/`run_tool`/`call_tool` method —
  there is no executor to call.
- **Response mapping** — usage and nanosecond→millisecond conversion;
  `done_reason == "length"` sets `truncated=True` and appends a warning;
  empty content appends a warning and is never replaced with invented text.
- **Failures and retries** — connect error → `ModelUnavailableError`; read
  timeout → `ModelTimeoutError`; a missing tag → `ModelUnavailableError`
  listing the installed tags; `503` retried exactly `MODEL_MAX_RETRIES` times
  then raises; `400` is never retried; a short deadline with a high retry
  count still returns well under the deadline's slowest possible full-backoff
  time, proving the wall-clock cap is honored regardless of the retry count.
- **Health and API** — `health()` reachable / unreachable / model-absent;
  `GET /models/status` returns the documented 200 shape and never leaks the
  base URL, a credential, or prompt text; returns 503 when unreachable.
- **Runtime abstraction** — `MODEL_RUNTIME=vllm` raises `NotImplementedError`
  on every gateway method, never a silent fallback to Ollama.

`tests/test_foundation.py` required no change: Phase 4A adds no database
model and no table, so its model/table count assertion (12) is unaffected.

### Mid-phase addition: the `think` parameter

The first live-validation run surfaced a serious finding (below) that
required a real code change mid-phase, per explicit instruction: a
`think: bool | None = None` parameter was added end to end (`ModelGateway`'s
three `generate_*` methods → the `ModelRuntime.chat()` Protocol →
`ollama_runtime.py`, the only place it is mapped onto Ollama's wire `think`
field; `vllm_runtime.py`'s docstring documents it as Ollama-specific,
ignore-or-map for a future implementer). `None` sends nothing — **no default
behavior changed**. One new test
(`RequestConstructionTests.test_think_sent_when_set_and_omitted_when_none`)
asserts it is sent when explicitly set and omitted when `None`.

## Live validation (real Ollama)

```powershell
# repository root — Ollama must already be running with MODEL_NAME installed
ollama list
# backend/
.\.venv\Scripts\python.exe -m scripts.smoke_model_gateway
```

`scripts/smoke_model_gateway.py` makes real HTTP calls to a real local Ollama
instance — no fake transport. Every prompt is synthetic/invented (fictional
tag `ZZ-9999`); the script never reads any file under `data/evaluation/`, and
`data/evaluation/manifest.json`'s recorded hashes were verified unchanged
both before this phase's changes and again after this validation run (see
Evaluation-asset firewall, below).

### Discovered model tag (Step 0 — never guessed)

```text
configured_model: qwen3.5:9b
installed_tags:   ["qwen3.5:9b"]
```

`MODEL_NAME=qwen3.5:9b` in the root `.env` came from `ollama list` on this
machine, not a guess. Ollama runtime version: `0.34.0`. Model: 9.7B
parameters, `Q4_K_M` quantization, digest `6488c96f…`, 6,594,474,711 bytes on
disk. Hardware: Windows 11, NVIDIA GeForce RTX 2050 (4 GB VRAM, partial
offload — 1,656,404,048 bytes resident in VRAM out of ~6.28 GB loaded), 12
CPU threads.

### The critical finding: thinking mode and structured output

`qwen3.5:9b` is a reasoning-capable ("thinking") model, on by default. This
was verified as a genuine correctness problem, not only a latency one:

| Call | Default (think on) | think=False |
| --- | --- | --- |
| Plain one-word reply | **41.787s**, 131 reasoning tokens spent, correct output | **1.201s**, 2 tokens, correct output |
| Schema-constrained extraction, 256-token budget | **160.039s**, `content` came back **empty**, `done_reason=length` — the entire token budget was consumed by the (unconstrained) reasoning trace and the schema-constrained JSON was never reached. `StructuredOutputError`: `"Expecting value: line 1 column 1 (char 0)"`. | **12.039s**, valid, schema-conformant JSON on the first attempt |

This is why every functional call in the smoke script (steps 3–8) passes
`think=False`: with the runtime's own default, structured/tool-call
generation does not merely get slower, it can **fail outright** within any
practical token budget. This is recorded as a **Phase 4B blocker** in
`docs/phase4a.md`'s Limitations — someone must decide the default `think`
policy for agent calls before Phase 4B's structured-output-heavy agent loop
can be considered safe to build against this model/runtime combination.

### Per-call latency (min / median / max, seconds — every functional call used `think=False`)

| Call type | n | min | median | max |
| --- | ---: | ---: | ---: | ---: |
| Plain generation | 3 | 0.699 | 0.925 | 2.024 |
| Structured output | 2 | 12.914 | 16.830 | 20.746 |
| Structured output, repair path exercised | 1 | 10.180 | 10.180 | 10.180 |
| Tool-call request | 1 | 11.471 | 11.471 | 11.471 |
| Timeout probe (time to raise, not to generate) | 1 | 1.014 | 1.014 | 1.014 |

First-call (cold) load: **2.470s** (reported separately from warm latency,
per the Phase 3B2 convention — this includes `load_ms=9.3` from Ollama's own
timing, i.e. the model was already resident from prior validation runs;
this is *not* a cold-start-from-unloaded measurement).

**Honesty note on the repair-path number:** the smoke script deliberately
sent an adversarial prompt (asking the model to write `confidence` as a word
instead of a number) to try to force a real repair round-trip. The model
extracted correct, schema-conformant JSON anyway on the **first** attempt
(`repair_attempts: 0`) — a good robustness result, but it means the
10.180s figure above is a single successful call, **not** an empirically
measured multi-turn repair latency. No genuine repair round-trip was
triggered in this live run (none of steps 4, 4b, or 5 needed one); the
gateway's repair mechanism itself is verified only by the mocked-transport
unit tests (`StructuredOutputTests.test_invalid_then_repaired`), which do
force and measure a real second round-trip, just not against a live model.
This is disclosed rather than glossed over: whether a live repair round-trip
costs roughly double a single call (the mechanistic expectation, since it is
a second full `/api/chat` request) is not yet confirmed against a live model.

### Other live results

- **Determinism probe:** identical output ("steady") across two calls at
  temperature 0, seed 42 — reported as a measurement, not asserted, per
  Ollama's own lack of a cross-batch determinism guarantee.
- **Timeout probe:** a deliberate 1-second deadline raised `ModelTimeoutError`
  in 1.014s — not swallowed, not silently succeeded.
- **`GET /models/status`** (through the real FastAPI route): 200, reachable,
  `configured_model_present: true`, `available_models: ["qwen3.5:9b"]`. Body
  contained no occurrence of the base URL (`11434`) or any variant of
  `base_url` — confirmed by direct string search over the JSON response.
- **`GET /api/ps`** (loaded models): `qwen3.5:9b` loaded, 6,280,676,635 bytes,
  `Q4_K_M`.
- **Tool call:** `lookup_synthetic_fixture` called with
  `{"tag": "ZZ-9999"}`, `finish_reason: "tool_calls"` — parsed and returned;
  nothing was executed (there is no executor in this package).

Full machine-readable report:
`data/evaluation/results/phase4a_model_gateway_smoke.json` (git-ignored).

## Phase 3A / 3B1 / 3B2 / 3C regression

```powershell
.\.venv\Scripts\python.exe -m scripts.smoke_knowledge
.\.venv\Scripts\python.exe -m scripts.smoke_pid --fresh
.\.venv\Scripts\python.exe -m scripts.smoke_hybrid
.\.venv\Scripts\python.exe -m scripts.smoke_structured --fresh
```

Run sequentially, after the model-gateway smoke, exactly as instructed (they
compete for CPU and compare global point/row counts):

- **Phase 3A** (`smoke_knowledge`): exit 0 — PDF ingestion, embedding, and
  citation-ready retrieval still work; duplicate detection unaffected.
- **Phase 3B1** (`smoke_pid --fresh`): exit 0 — P&ID OCR processing, tagging,
  and artifact generation still work.
- **Phase 3B2** (`smoke_hybrid`): exit 0 — hybrid dense/sparse/RRF/reranked
  retrieval, the Qdrant dense-backup preservation check, and the sparse
  backfill idempotence check all still pass.
- **Phase 3C** (`smoke_structured --fresh`): exit 0 — maintenance/sensor CSV
  ingestion, equipment-tag normalization, and feature/anomaly computation
  still work; the vibration fixture still reports `relative_increase`, never
  a diagnosis.

No Phase 0–3C endpoint, schema, or contract was modified; the model gateway
is entirely additive (one new route, one new package, no shared service
touched).

## Evaluation-asset firewall

```powershell
Get-FileHash data\evaluation\model_eval_cases.jsonl -Algorithm SHA256
Get-FileHash data\evaluation\model_eval_config.json -Algorithm SHA256
Get-FileHash data\evaluation\README.md -Algorithm SHA256
```

Compared against `data/evaluation/manifest.json`'s recorded hashes — **all
three unchanged**, checked both before implementation started and again
after the full live validation run:

| File | Status |
| --- | --- |
| `model_eval_cases.jsonl` (38,755 bytes) | OK |
| `model_eval_config.json` (1,244 bytes) | OK |
| `README.md` (1,443 bytes) | OK |

No smoke-test prompt, fixture, or unit test references any evidence ID, case
ID, expected answer, or scoring note from the benchmark; every synthetic
prompt uses the invented tag `ZZ-9999`, absent from the benchmark corpus
(confirmed by a direct grep before writing the script).

## Frontend / repository-wide checks

```powershell
# frontend/
npm run build
npm run lint
# repository root
git diff --check
docker compose -f infra/docker-compose.yml config --quiet
```

All four pass. No frontend change and no `infra/docker-compose.yml` change
were needed for Phase 4A.
