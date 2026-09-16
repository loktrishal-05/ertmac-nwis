# Phase 4B validation report

Self-audit gate run retroactively at the start of the Phase 4C-4F autonomous
continuation, 2026-09-17, per `docs/phase4-autonomous-continuation.md` §4.

## Gate results

1. `python -m compileall -q app alembic scripts tests` — clean, no output.
2. `python -m unittest discover -s tests` — **169 tests, OK** (168 pre-existing
   Phase 4B/4A/3C/3B2/... tests + 1 new evaluation-asset hash guard test added
   in this session, see D-003). No regression from any prior phase.
3. `python -m pip check` — "No broken requirements found."
4. `python -m alembic upgrade head` — already at `0004_agent_runs` (head).
5. `python -m alembic check` — "No new upgrade operations detected."
6. Evaluation-asset hash guard
   (`tests/test_evaluation_asset_guard.py`) — pass; see D-003.
7. `git diff --check` — no conflict markers or whitespace errors; only
   informational LF/CRLF normalization notices from Windows git config.
8. Sub-phase safety-property checklist:
   1. Every test from every prior phase still passes, unchanged: 169/169,
      delta +1 (the new hash-guard test; no prior test was touched).
   2. `alembic check`: no drift.
   3. Evaluation-asset hash: byte-identical (pinned this run, D-003).
   4. No module under `app/agents/` names a hosted-provider or hosted-tracing
      hostname, and none imports `ollama_runtime` or reads `MODEL_BASE_URL`
      directly: enforced by `tests/test_agents.py::SourceGuardTests` (checked
      against the 4A `HOSTED_HOSTNAMES`/telemetry-hardening lists) — pass.
   5. The tool registry is read-only by construction: enforced by
      `SourceGuardTests::test_no_write_tool_vocabulary_in_the_registry` and
      `RegistryTests` — pass.
   6. No prompt, fixture, test or smoke query contains benchmark content:
      `app/agents/prompts/router.py` is built from the route vocabulary only
      (`RouterNodeTests::test_router_prompt_uses_only_the_seven_routes`);
      manually re-read against `docs/model-evaluation-spec.md` §3 "### Routes"
      during this audit — no case ID, scenario, or expected value present.
   7. No trace row, log line or error string carries prompt bodies or
      evidence body text: `app/agents/tracing.py` persists `evidence_id`
      strings only (`TracingTests`); `MODEL_LOG_PROMPTS` defaults false
      (Phase 4A).
   8. Sub-phase safety property — "the deterministic fallback (confidence
      floor, structured-output failure) is a code path, not a prompt
      instruction, with a test that fails if the enforcement is removed":
      `RouterNodeTests::test_low_confidence_falls_back_to_clarification_with_warning`
      and `::test_structured_output_error_falls_back_to_clarification` both
      assert the fallback fires from `app/agents/nodes/router.py` control
      flow; removing either `if` branch in that file fails the corresponding
      test. Pass.

**Gate result: PASS.** No item required a retry or a `BLOCKED` mark.

## Test total and delta

169 tests total. +1 versus the 168 present when this session began (the
evaluation-asset hash guard, D-003) — no other test file was touched.

## Scope confirmation

No LangGraph, no agent reasoning beyond routing, no S1-S7 schema, and no
citation-validator *enforcement* exists yet as of this report — all of that
is explicitly 4C-4F scope. `app/agents/nodes/stubs.py` still reports
`sub_phase = "unassigned"` for every non-router route in the code as
committed with this report; D-004 (in `docs/phase4-decisions.md`) resolves
that mapping as 4C's first act, applied when 4C's node registration lands.
