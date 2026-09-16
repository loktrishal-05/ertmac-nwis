# Phase 4B — LangGraph agent scaffold, router, tool registry, evidence & tracing

This report is written retroactively at the start of the Phase 4C-4F
autonomous continuation (see `docs/phase4-decisions.md` D-001). The code it
describes was already complete and passing in the working tree when the
autonomous run resumed; nothing in this report describes new work.

Phase 4B wires the Model Gateway (4A) into a real agent graph and builds
every piece of cross-cutting infrastructure 4C-4F depend on, without
implementing any specialist agent's reasoning:

```text
React → FastAPI → LangGraph → Agent Nodes → Model Gateway → Local Runtime
                    (4B)         (4B router;
                                  4C-4F stubs)
```

## What 4B built

- **`app/agents/state.py`** — `WorkbenchState`, the LangGraph state contract.
  Accumulating fields (`evidence`, `warnings`, `errors`, `tool_invocations`,
  `step_records`) use `Annotated[list[X], operator.add]` reducers so an
  early-recorded warning can never be silently overwritten by a later node's
  return value.
- **`app/agents/evidence.py`** — `EvidenceRef`, one discriminated union over
  four evidence kinds (`document_chunk`, `pid_region`, `csv_row`,
  `sensor_window`) unifying Phase 3A/3B1/3B2/3C provenance into a single
  shape the citation validator can check against. `evidence_id` is always a
  SHA-256 of `kind:source_sha256:stable_key` — deterministic across runs,
  never `hash()`/`id()`.
- **`app/agents/citations.py`** — `validate_citations()`, a pure function
  reporting unknown/uncited IDs. Built and exhaustively tested here, with no
  agent output yet to rationalize it against; enforcement is 4C's job.
- **`app/agents/registry.py`** — the tool registry: enumerable
  (`list_tools()`), closed (`get_tool()` raises on anything unregistered,
  and there is no runtime registration path), and every call validates
  arguments through a Pydantic model with `extra="forbid"` before an adapter
  ever runs.
- **`app/agents/tools/`** — 7 read-only tools registered at import time:
  `retrieve_documents`, `get_pid_regions` (knowledge.py, wrapping 3A/3B1/3B2
  read paths), `get_maintenance_history`, `get_work_order` (maintenance.py,
  wrapping 3C), `get_sensor_readings`, `get_latest_reading`,
  `compute_sensor_features` (sensors.py, wrapping 3C). Every window/limit
  argument is clamped in `tools/base.py` against
  `AGENT_TOOL_MAX_WINDOW_DAYS` / `STRUCTURED_QUERY_MAX_LIMIT` before it
  reaches a Phase 3C query, since those services load matching rows into
  memory with no pagination.
- **`app/agents/nodes/router.py`** — the one real node in 4B. Classifies a
  query into one of the 7 routes via `generate_structured` with `think=False`
  (justified by the Phase 4A latency/failure measurements). A
  `StructuredOutputError` or a confidence below `AGENT_ROUTER_MIN_CONFIDENCE`
  falls back to `clarification` **in code**, never a default agent — the
  deterministic fallback is not a prompt instruction.
- **`app/agents/prompts/router.py`** — the router's system prompt and the 7
  route names/descriptions, built from `docs/model-evaluation-spec.md`'s
  route vocabulary in this module's own words. No case content.
- **`app/agents/nodes/stubs.py`** — a typed not-implemented node for every
  non-router route. A stub never produces prose, never calls the gateway,
  never calls a tool; it only proves the graph wiring is correct.
  `sub_phase = "unassigned"` was left explicit in 4B rather than guessed —
  4C's first act (D-004) is resolving that mapping.
- **`app/agents/graph.py`** — builds and compiles the `StateGraph`, one
  `router` node fanning out via conditional edges to one node per route, each
  wrapped by `_traced()` so every node execution produces exactly one
  `step_records` entry regardless of whether it called the gateway. Sync
  throughout (`graph.invoke()`, never `ainvoke()`) since the whole stack is
  sync. No checkpointer — `app/agents/tracing.py`'s own tables are the
  auditable record.
- **`app/agents/tracing.py`** + `AgentRun`/`AgentRunStep` models + migration
  `0004_agent_runs` — persists one row per run and one row per graph step.
  Only `evidence_id` strings ever reach these tables, never evidence bodies,
  retrieved text, or sensor values. Query text is stored only when
  `AGENT_TRACE_STORE_QUERY` is true; recording is a no-op when
  `AGENT_TRACE_ENABLED` is false.
- **`POST /query`** (`app/api/routes/query.py`) — runs the graph, records the
  trace, returns route/evidence/warnings/`human_approval_required`/
  `action_class`/per-step timings. Model-gateway failures map to 502/503/504.
- **`GET /agents/status`** (`app/api/routes/agents.py`) — enumerates the 7
  routes (all `not_implemented` at this point), the read-only tool registry,
  and gateway health. Never returns a base URL, credential, or prompt body.

## What 4B deliberately did not build

- No specialist agent reasoning — every non-router route is a stub.
- No S1-S7 output schemas — those are 4C-4F deliverables, derived from
  `docs/model-evaluation-spec.md` §4 (permitted: shapes, not case content).
- No citation *enforcement* — the validator exists and is tested in
  isolation; nothing calls it on a rejection path yet.
- No approval/guardrail enforcement of `human_approval_required` /
  `action_class` — they are recorded fields only, per the Phase 5 boundary.

## Configuration added

`AGENT_ROUTER_MIN_CONFIDENCE` (0.5), `AGENT_TOOL_MAX_WINDOW_DAYS` (90),
`AGENT_MAX_STEPS` (12), `AGENT_TRACE_ENABLED` (true),
`AGENT_TRACE_STORE_QUERY` (true), `AGENT_RUN_TIMEOUT_SECONDS` (300). None of
these carry a configured anomaly threshold, equipment tag, or route default —
every one of those must arrive from the caller or cited evidence, by design,
so a later sub-phase cannot quietly acquire a hardcoded limit through a
config default.

## Safety properties already enforced in code, with tests

- The tool registry is closed and read-only by construction
  (`RegistryTests`, `SourceGuardTests::test_no_write_tool_vocabulary_in_the_registry`).
- No agent source file names a hosted inference provider or hosted tracing
  endpoint (`SourceGuardTests` in `tests/test_agents.py`).
- Router confidence-floor and structured-output-failure fallbacks are code
  paths, not prompt instructions (`RouterNodeTests`).
- `step_records`/tracing carry evidence **IDs** only, never bodies
  (`app/agents/tracing.py` docstring + `TracingTests`).

See `docs/phase4b-validation.md` for the self-audit gate run and test counts.
