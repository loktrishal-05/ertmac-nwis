# Phase 4B — LangGraph state, orchestrator, tool layer

Builds the agent-orchestration substrate on top of Phase 4A's model gateway:
a LangGraph `StateGraph`, a deterministic router node, a closed read-only
tool registry wrapping Phase 3A/3B1/3B2/3C's own read functions, a citation
validator, a run-tracing store, and extended `POST /query` / `GET
/agents/status` contracts. **No route beyond routing itself reasons yet** —
every one of the seven routes resolves to a typed `not_implemented` stub.
That is deliberate: this phase proves the wiring, not the agents.

## Package layout

```
app/agents/
  __init__.py       # telemetry hardening (see Sovereignty) + public exports
  state.py           # WorkbenchState TypedDict, ToolInvocationRecord
  evidence.py        # EvidenceRef (4 kinds), make_evidence_id, factories
  citations.py       # validate_citations — built + tested, NOT enforced (4C)
  registry.py        # closed, enumerable, read-only-by-construction tool registry
  tracing.py         # record_run() — persists AgentRun + AgentRunStep rows
  tools/
    base.py           # clamp_limit, clamp_window
    knowledge.py       # retrieve_documents, get_pid_regions
    maintenance.py      # get_maintenance_history, get_work_order
    sensors.py          # get_sensor_readings, get_latest_reading, compute_sensor_features
  prompts/
    router.py          # ROUTE_NAMES, ROUTES, ROUTER_SYSTEM_PROMPT — the only prompt
  nodes/
    router.py          # router_node — the only node that calls the gateway
    stubs.py            # make_stub_node — one per route, all not_implemented
  graph.py            # build_graph, get_graph (singleton), run_graph, _traced
```

## The graph

```
START -> router -> {knowledge | maintenance | safety | process_optimization |
                     combined_safety_maintenance | guardrail_refusal |
                     clarification} -> END
```

Synchronous (`graph.invoke`, never `ainvoke`): the Phase 4A gateway and
every existing service in this repository are sync, and introducing one
async layer into an otherwise sync stack buys nothing. No checkpointer:
runs are single-shot, and `tracing.py`'s own tables are the auditable
record — conflating them with LangGraph's own persistence would blur which
one is authoritative. `get_graph()` is a lazy `@lru_cache(maxsize=1)`
singleton, the same pattern as `get_model_gateway()`, `get_embeddings()`,
and `get_reranker()`.

Every node is wrapped by `_traced()`, which times the call and appends one
`step_records` entry regardless of whether the node called the model
gateway. A node may return transient `_usage`/`_timings` keys (only
`router_node` does, since it is the only node that calls the gateway in
this phase); `_traced()` strips them into the step record and they never
reach `WorkbenchState` itself.

## The router — the only reasoning in this phase

`router_node` calls `gateway.generate_structured(..., schema=RouteDecision,
think=False)`. `think=False` is not a stylistic choice: Phase 4A's live
measurements (`docs/phase4a-validation.md`) showed the installed
`qwen3.5:9b` build defaulting to an extended thinking trace that consumed
an entire 256-token budget before reaching JSON, versus a valid response in
~12.5s with thinking off. The router runs on every single query, so that
finding is load-bearing here, not just informative.

Deterministic fallback lives in **code**, never in the prompt:

- `StructuredOutputError` (the model's output never satisfied `RouteDecision`
  after Phase 4A's bounded repair) → route = `clarification`, confidence 0.0.
- `confidence < AGENT_ROUTER_MIN_CONFIDENCE` → route = `clarification`,
  the model's own (low) confidence and reasoning are still recorded, plus a
  warning naming the configured floor.
- Otherwise → the model's own route, confidence, and reasoning, unmodified.

A misrouted query answered confidently by the wrong specialist is worse
than an honest "I need clarification" — this rule is what encodes that.

## Evidence and the citation validator

`EvidenceRef` is one discriminated union over four kinds —
`document_chunk`, `pid_region`, `csv_row`, `sensor_window` — unifying
Phase 3A/3B2 chunk citations, Phase 3B1 P&ID OCR regions, and Phase 3C
CSV/sensor rows into the shape the (future) citation-enforcing agents and
the tool registry both use. Every `evidence_id` is `sha256(kind :
source_sha256 : stable_key)[:16]`, never `hash()`/`id()` (per-process,
non-reproducible). Each variant hashes its **most specific** stable key —
`chunk_id`, `region_id`, `source_row_number`, `citation_label` — rather
than the human-readable `locator` alone: two distinct chunks reported as
"page 3" must not collide just because their locator string does.

`validate_citations(*, emitted, available)` is a pure function: no
database access, no model call, and it never raises — it reports
`unknown_ids` (a citation that names evidence not gathered this turn) and
`uncited_evidence_ids` (gathered but never referenced) separately, since
only the first makes an answer invalid. It is built and exhaustively
tested here, in 4B, while there is no agent output yet to unconsciously
tune it against. **Enforcement is Phase 4C's job**, not this one's.

## The tool registry — the safety boundary

Seven tools, each wrapping exactly one existing Phase 3A/3B1/3B2/3C read
function, never a write path:

| Tool | Wraps |
|---|---|
| `retrieve_documents` | `app.services.retrieval.retrieve` |
| `get_pid_regions` | P&ID manifest + region JSON artifact read |
| `get_maintenance_history` | `structured_queries.maintenance_history` |
| `get_work_order` | `structured_queries.work_order_lookup` |
| `get_sensor_readings` | `structured_queries.sensor_readings_query` |
| `get_latest_reading` | `structured_queries.sensor_latest` |
| `compute_sensor_features` | `structured_queries.sensor_features_query` |

The registry is closed and enumerable: `register()` is called only at
import time by `app/agents/tools/*.py`; there is no dynamic registration
path and no plugin loader, so `list_tools()` is always the complete set.
Every tool's arguments are a Pydantic model with `extra="forbid"` —
`RegisteredTool.invoke()` wraps any validation failure in
`ToolArgumentError`, never a bare/generic exception. Every window/limit
argument is clamped (`clamp_limit` against `STRUCTURED_QUERY_MAX_LIMIT`,
`clamp_window` against the new `AGENT_TOOL_MAX_WINDOW_DAYS`) before it
reaches a Phase 3C query — Phase 3C's read services load matching rows
into memory with no pagination, so an agent-chosen unbounded range is a
denial-of-service on our own backend.

Two things preserved exactly from earlier phases, because getting either
wrong silently produces confidently-wrong output:

- **`measurement` → `sensor_type`.** `SensorReading` has no `measurement`
  column; the agent-facing argument is named `measurement` and forwarded
  verbatim into `sensor_readings_query(measurement=...)`, which maps it
  internally. `compute_sensor_features` never invents a threshold default —
  `thresholds=arguments.thresholds or SensorFeatureThresholds()` is an
  empty/all-`None` object when the caller supplies none, never a hardcoded
  number.
- **OCR status.** `get_pid_regions`' `_ocr_status` reuses Phase 3B1's exact
  rule: confidence < 0.6 is `ambiguous`, otherwise `unverified` — OCR
  confidence never establishes `verified`.

## Sovereignty: the LangGraph dependency tree

`langgraph==1.2.11` pulls in `langchain-core==1.6.3`. Auditing the
resolved tree (`pip show`, `pip list`) surfaced `langsmith` as a transitive
dependency — a hosted tracing client that, if enabled, would call
`smith.langchain.com`. It is never enabled by anything in this codebase,
but "never enabled by us" is not the same guarantee as "cannot be
enabled by accident," so it is hardened defensively rather than left to
`.env` alone:

```python
# app/agents/__init__.py — runs before any submodule import below it
_TELEMETRY_DEFAULTS = {
    "LANGCHAIN_TRACING_V2": "false", "LANGSMITH_TRACING": "false",
    "LANGCHAIN_ENDPOINT": "", "LANGSMITH_ENDPOINT": "",
}
for _key, _value in _TELEMETRY_DEFAULTS.items():
    os.environ.setdefault(_key, _value)
```

`os.environ.setdefault`, not assignment: an operator can still deliberately
override it via the real environment. This runs at package `__init__`
import time — before `graph.py`'s `from langgraph.graph import ...` — so it
is set regardless of which module inside `app.agents` is imported first.
`test_agents.py`'s `SourceGuardTests` extends Phase 4A's hosted-provider
hostname guard to every file under `app/agents/`, adds the three LangSmith
hostnames to the scanned denylist, and asserts the telemetry variables and
`setdefault` literally appear in `__init__.py`'s source.

## Tracing

`agent_runs` (one row per `run_graph()` call) and `agent_run_steps` (one
row per traced node) are new in migration `0004_agent_runs` — the first
Phase 4 schema change. `record_run()` is a no-op when
`AGENT_TRACE_ENABLED=false`; `AGENT_TRACE_STORE_QUERY=false` stores every
other field but leaves `query_text` `NULL`. Only `evidence_id` **strings**
ever reach `agent_run_steps.evidence_ids` — never an `EvidenceRef` body,
never retrieved text, never an OCR quote, never a sensor value.

## New configuration

No configured default anomaly threshold, equipment tag, or route — every
one of those must still arrive from the caller or from cited evidence, per
the same discipline as Phase 3C and 4A.

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_ROUTER_MIN_CONFIDENCE` | `0.5` | Below this, force `clarification` |
| `AGENT_TOOL_MAX_WINDOW_DAYS` | `90` | Hard cap on any tool's date span |
| `AGENT_MAX_STEPS` | `12` | `recursion_limit` passed to `graph.invoke` |
| `AGENT_TRACE_ENABLED` | `true` | Master switch for `record_run()` |
| `AGENT_TRACE_STORE_QUERY` | `true` | Whether `query_text` is persisted |
| `AGENT_RUN_TIMEOUT_SECONDS` | `300` | Recorded; not yet enforced as a hard deadline |

## `POST /query` and `GET /agents/status`

Both extend, rather than replace, their Phase 2 placeholder shape.
`QueryRequest` is now `extra="forbid"`, rejecting any attempt to route
`model`/`runtime`/`base_url`/`temperature` through a per-request field —
those remain operator configuration only. `QueryResponse` returns the
route decision, its confidence and reasoning, the stub `agent_result`,
gathered evidence (always `[]` in this phase — stub nodes never call a
tool), warnings, the recorded-but-unenforced `human_approval_required` /
`action_class` fields, and per-step timings. Gateway failures map to HTTP
status explicitly: `ValueError → 422`, `ModelUnavailableError → 503`,
`ModelTimeoutError → 504`, `ModelRuntimeError → 502`.

`GET /agents/status` enumerates the seven routes (all `not_implemented`,
`sub_phase: "unassigned"` — see Limitations), the full tool registry
(name, description, `read_only: true`), and delegates gateway health to
Phase 4A's own `get_model_gateway().health()` — it never re-probes and
never exposes a base URL, API key, or prompt body.

## Limitations

- **`sub_phase` is `"unassigned"` for every route, not a guess.** No
  authoritative source in this repository maps a specific route to one of
  4C/4D/4E/4F; inventing that mapping here would repeat the exact mistake
  the "discover, don't invent" discipline exists to prevent. It is a fact
  visible in `GET /agents/status`, not silently hidden.
- **No citation enforcement, no relevance floor, no guardrail, no HITL
  gate, no audit hash chaining.** `human_approval_required` and
  `action_class` are recorded fields nothing in this phase writes to
  anything but their default. All of the above are later work.
- **No streaming, no checkpointer.** Single-shot invoke only.
- **Evidence is always empty in this phase.** Stub nodes never call a
  tool; the tool registry and its 7 adapters are proven correct by unit
  test and are wired into the graph's *reachability*, not yet into any
  node's *behavior*.
