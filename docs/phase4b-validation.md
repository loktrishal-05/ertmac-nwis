# Phase 4B — Validation

## Deterministic backend tests

```
# backend/
.venv/Scripts/python.exe -m unittest discover -s tests -v
...
Ran 168 tests in 57.948s
OK
```

168 tests total, all passing: 58 new in `tests/test_agents.py`, 8 in
`test_foundation.py` (2 updated for this phase's contract extension — see
below), 39 in `test_model_gateway.py` (unchanged, all still pass — no
Phase 4A regression), and 63 across `test_knowledge.py` / `test_pid.py` /
`test_hybrid.py` / `test_structured.py` (unchanged). Before this phase the
suite stood at 110 tests; the delta is +58, entirely new coverage.

`test_agents.py` fake-transport/fake-gateway discipline, no live Ollama
and no live DB in any of its 58 tests:

- **Evidence** (7): determinism, SHA-256 derivation, non-collision of two
  distinct chunks sharing a human-readable locator, all four factory
  shapes, `extra="forbid"`.
- **Citation validator** (4): all-cited valid, unknown id invalidates,
  uncited-but-gathered does not invalidate, empty/empty.
- **Registry** (6): exactly the seven tools registered once, duplicate
  registration raises, unknown tool raises `ToolNotFoundError`, an extra
  or missing argument raises `ToolArgumentError` (never a bare exception),
  `invoke_tool` calls the bound adapter.
- **Tool base** (5): `clamp_limit` under/over cap, `clamp_window`
  short/long/one-sided spans.
- **Knowledge/maintenance/sensor tool adapters** (10): evidence + payload
  shape against mocked Phase 3A/3B1/3B2/3C service functions; missing
  P&ID version / non-P&ID version / missing manifest artifact all report
  as a *warning*, never an exception; the `measurement` argument is
  asserted to reach `sensor_readings_query` **unrenamed**; a work-order
  miss is asserted `found: False`, not an error; `compute_sensor_features`
  is asserted to pass an empty/all-`None` `SensorFeatureThresholds()`
  when the caller supplies none — never a hardcoded number.
- **Router node** (4): confident decision routes directly with
  `_usage`/`_timings` present; low confidence falls back to
  `clarification` with a warning naming the configured floor;
  `StructuredOutputError` falls back to `clarification` with confidence
  0.0 and no usage/timings; the prompt is built from exactly the seven
  routes.
- **Stub nodes** (2): every route's stub reports
  `{"status": "not_implemented", "sub_phase": "unassigned", ...}`.
- **Graph** (4): `build_graph()` routes to the matching stub and records
  exactly two steps (router + stub) with populated durations; the route
  selector falls back to `clarification` on an unrecognized route;
  `get_graph()` is a cached singleton; `run_graph()` populates `run_id`
  and both timestamps.
- **Tracing** (3): `record_run()` persists one `AgentRun` and the matching
  `AgentRunStep` rows with `evidence_ids` intact; `AGENT_TRACE_STORE_QUERY
  = false` nulls `query_text` while leaving route/confidence intact;
  `AGENT_TRACE_ENABLED = false` is a true no-op (`session.add` never
  called).
- **Config** (4): defaults match `.env.example`; `AGENT_ROUTER_MIN_CONFIDENCE`
  and `AGENT_TOOL_MAX_WINDOW_DAYS` and `AGENT_RUN_TIMEOUT_SECONDS` bounds
  are enforced by `ValidationError`.
- **Source guard** (4): no file under `app/agents/` names a hosted
  inference provider or a hosted LangSmith tracing hostname; the
  telemetry-hardening variables and `setdefault` are literally present in
  `__init__.py`'s source; no registered tool name contains write
  vocabulary (`delete`/`update`/`insert`/`write`/`ingest`).
- **API routes** (5): `POST /query` rejects an extra field and an empty
  query with 422; a mocked-gateway run returns the extended contract and
  is confirmed to have called `session.add`; `GET /agents/status`
  enumerates all seven routes and all seven tools, reports `read_only:
  true` for each, and never renders `base_url` or `api_key` into the
  response body.

## Live validation (real Ollama, real Postgres)

```
# backend/
.venv/Scripts/python.exe -m scripts.smoke_agents
```

```
Phase 4B agent orchestration smoke validation passed.
  configured model: qwen3.5:9b
  registered tools: ['compute_sensor_features', 'get_latest_reading',
    'get_maintenance_history', 'get_pid_regions', 'get_sensor_readings',
    'get_work_order', 'retrieve_documents']
  route classification agreement: 5/7
  latency summary (seconds):
    agents_status: n=1 min=0.644 median=0.644 max=0.644
    query: n=7 min=24.85 median=33.05 max=61.748
```

### Route classification — 5/7 agreement, reported honestly

Seven synthetic (fictional tag `ZZ-8888`, distinct from Phase 4A's
`ZZ-9999`) queries were sent through `POST /query`, one per route, and the
**real** model's classification was recorded rather than asserted:

| Intended route | Actual route | Confidence | Matched |
|---|---|---|---|
| knowledge | knowledge | 0.95 | yes |
| maintenance | maintenance | 0.95 | yes |
| safety | safety | 0.95 | yes |
| process_optimization | **guardrail_refusal** | 0.95 | **no** |
| combined_safety_maintenance | **clarification** | 0.95 | **no** |
| guardrail_refusal | guardrail_refusal | 0.95 | yes |
| clarification | clarification | 0.95 | yes |

The two misses are not classifier noise — the model's own `route_reasoning`
names the cause both times: the probe queries were deliberately prefixed
with disclosure language ("This is a synthetic software-validation query,
not a real operational request") to keep the benchmark firewall and
sovereignty-review discipline intact, and the router — correctly following
its own instruction to prefer the more cautious route under ambiguity —
read that disclosure as grounds for `guardrail_refusal` or `clarification`
rather than as neutral metadata. This is a genuine interaction between
"always disclose synthetic test data" and "prefer caution under
ambiguity," not a router defect, and it is recorded here rather than
smoothed over or re-run until it matched. It is also informative for 4C+:
a real operator's queries won't carry this disclosure, so it should not
recur in production traffic, but a router prompt revision that makes
"this is a test" framing less safety-coded may be worth a later look.

All five confident matches, and both misses, still routed to one of the
seven legal routes, still produced a typed `not_implemented` stub result,
and still traced two steps (router + stub) — the wiring under test held in
every case; only the model's own judgment call varied.

### Tracing verified against the live database

```json
{
  "run_id": "ea3ff19a-3b54-42d3-be00-bab44786704c",
  "status": "ok", "route": "knowledge", "query_text_stored": true,
  "step_count": 2, "step_node_names": ["router", "knowledge"],
  "router_step_usage": {"total_tokens": 471, "prompt_tokens": 356, "completion_tokens": 115},
  "router_step_timings": {"eval_ms": 42292.39, "load_ms": 10.21, "total_ms": 61525.77, "prompt_eval_ms": 2430.06}
}
```

Read back from Postgres with a **fresh** session (not the request-scoped
one `record_run` used) after the HTTP response returned: one `AgentRun`
row and exactly two `AgentRunStep` rows exist for the sampled run, the
router step carries non-empty usage/timings from the live gateway call,
and the stub step's `evidence_ids` is `[]` — exactly as expected, since no
tool is called in this phase.

### `GET /agents/status`, live

Confirmed live (not just under a mocked gateway, as in the unit suite):
seven routes, seven tools, `read_only: true` on every tool, and gateway
health delegated to Phase 4A's `get_model_gateway().health()` with no
re-probe and no base URL / API key in the response.

### Rejection contract unchanged

`{}`, `{"query": "   "}`, and `{"query": "x", "model": "other"}` all
returned 422 against the live server, exactly as the Phase 2 stub
contract did — the new `extra="forbid"` on `QueryRequest` is confirmed
live, not just under `TestClient`.

## Phase 3A / 3B1 / 3B2 / 3C / 4A regression

```
# backend/
.venv/Scripts/python.exe -m scripts.smoke_knowledge          # exit 0
.venv/Scripts/python.exe -m scripts.smoke_pid --fresh         # exit 0
.venv/Scripts/python.exe -m scripts.smoke_hybrid              # exit 0
.venv/Scripts/python.exe -m scripts.smoke_structured --fresh  # exit 0
.venv/Scripts/python.exe -m scripts.smoke_model_gateway       # exit 0
```

All five prior-phase live smokes pass unchanged after the Phase 4B
migration and code additions. `smoke_model_gateway`'s own thinking-mode
comparison reconfirms Phase 4A's finding on this run (`think=False`:
13.85s, schema-conformant; `think` on: 187.19s, schema validation
failed) — nothing in 4B altered that behavior.

## Migration and schema

```
# backend/
.venv/Scripts/python.exe -m alembic upgrade head   # 0003_structured_data -> 0004_agent_runs
.venv/Scripts/python.exe -m alembic check          # "No new upgrade operations detected."
```

`0004_agent_runs` adds `agent_runs` and `agent_run_steps` only; no
Phase 0–3C table was altered. `alembic check` is clean, including the
`route` index on `agent_runs`, which required adding `index=True` to the
ORM column to match the migration's explicit `create_index` — caught by
`alembic check` itself during this validation pass, fixed, and
re-verified clean.

## Evaluation-asset firewall

```
sha256sum model_eval_cases.jsonl model_eval_config.json README.md
```

All three hashes are byte-identical to `data/evaluation/manifest.json`.
`smoke_agents.py` re-verifies this same guard programmatically as its
first step, before any live call.

## Frontend / repository-wide checks

```
# frontend/
npm run lint    # clean
npm run build   # clean, unchanged bundle size (no frontend changes this phase)

# repository root
docker compose -f infra/docker-compose.yml config   # valid (untouched this phase)
git diff --check                                     # no whitespace errors (CRLF-normalization notices only)
```

## Deliberate contract changes to Phase 2/3 tests

`tests/test_foundation.py` asserted the Phase 2 placeholder shape of both
`POST /query` and `GET /agents/status` verbatim. Phase 4B's whole point is
to replace those placeholders with real routing, so two tests were
updated — not weakened, extended — to assert the new (documented, tested
above) contract shape instead of a fixed placeholder string:

- `test_query` now asserts the route is one of the seven legal routes,
  `agent_result.status == "not_implemented"`, and the extended-contract
  fields are present, rather than the old fixed placeholder body. It also
  now genuinely calls the live model gateway (the same server process the
  rest of the file already requires live Postgres for), so its request
  timeout was raised from the file's 5s default to 180s to absorb a cold
  model load — the only per-request timeout override in the file.
- `test_agents` now asserts the new `{routes, tools, gateway}` shape
  (seven routes, all tools read-only, `gateway.reachable` present)
  instead of the old five-name placeholder list.
- `test_metadata_and_offline_migration`'s model/table count assertions
  were bumped from 12 to 14 for the two new tables.

## Design decisions worth flagging explicitly

- **`sub_phase: "unassigned"`** on every route in `GET /agents/status` and
  every stub's `agent_result` — there is no authoritative route→sub-phase
  mapping in this repository to read, and inventing one would violate the
  same "discover, don't invent" rule this whole project is built on. See
  `docs/phase4b.md`'s Limitations section.
- **`step_records`** was added to `WorkbenchState` beyond the field list a
  literal reading of the state contract implies, because `tool_invocations`
  is legitimately always empty in this phase (no node calls a tool) yet
  per-node timing/usage tracing was still required. Documented in
  `state.py`'s own docstring.
- **`evidence_id` hashing** uses each variant's most specific stable key
  (`chunk_id`/`region_id`/`source_row_number`/`citation_label`), not the
  human-readable `locator` string, specifically to avoid collisions between
  distinct records that happen to render the same locator (e.g. two chunks
  both on "page 3"). Covered by
  `test_shared_locator_does_not_collide_across_distinct_chunks`.

## Limitations (see `docs/phase4b.md` for the full list)

No citation enforcement, no relevance floor, no guardrail/HITL/audit
logic, no streaming, no checkpointer, and evidence is always empty in this
phase — stub nodes never call a tool. All of the above are explicitly
out of scope for 4B and unchanged from what was scoped at the start of
this phase.
