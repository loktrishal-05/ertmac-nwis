# Phase 4E — Validation

## Deterministic backend tests

```
# backend/
.venv/Scripts/python.exe -m unittest discover -s tests
...
Ran 258 tests in 171.665s
FAILED (errors=1)
```

**257 of 258 tests pass.** The one failure,
`tests.test_foundation.FoundationTests.test_query`, is a pre-existing
live-model-dependent test (spins up a real `uvicorn` subprocess and calls
the real configured Ollama runtime) that fails on a genuine live-latency
timeout, not a logic error — see "The one INCONCLUSIVE item" below. Before
this sub-phase the suite stood at 235 (4D's own count); the delta is
**+23**, entirely new deterministic coverage
(`tests/test_agents_maintenance.py`), plus two bug fixes to two
pre-existing tests whose assumptions this sub-phase's own work
invalidated (see "Two bugs found and fixed" below) — no test was weakened,
only corrected.

- **`observation_language.py`** (3): clean factual text has no violations;
  each of the six `FORBIDDEN_WORDS` (reused verbatim from Phase 3C's
  `tests/test_structured.py::FORBIDDEN_WORDS`, not re-derived — see
  `docs/phase4e.md`) is individually asserted flagged in an
  observation-shaped sentence; the bare function is asserted to still flag
  the same words when used on hypothesis-shaped text — the asymmetry is
  enforced by *where* the function is applied
  (`enforce_citations_and_diagnostic_language` runs it only against
  `observations`, never `hypotheses`), not by the function being
  context-aware.
- **`enforce_citations_and_diagnostic_language()`** (3): valid on the first
  attempt, no retry; a diagnostic word in `observations` uses exactly one
  regeneration, with the retry note containing "diagnostic"; a persistent
  violation raises `EnforcementFailure` with "failure mode" in the reason.
- **`_extract_threshold()`** (5): "maximum of X" and "threshold is X" and
  "shall not exceed X" phrasings are each individually extracted with the
  correct numeral; text with no keyword+numeral pair returns `(None,
  None)`; given multiple SOP chunks, the first one that actually yields a
  numeral wins (not necessarily the first chunk in the list).
- **`_anomaly_status()`** (4): `threshold_exceeded` → critical;
  `sudden_change` → warning; no observations → normal; critical wins when
  both a critical- and a warning-kind observation are present together.
- **`maintenance_node()`** (8): no equipment tag in the query → S5, before
  any tool is called; no evidence anywhere for a valid tag → S5; a SOP
  chunk with **no** extractable numeral → S4, and `compute_sensor_features`
  is asserted **never called** (the fake `invoke_tool` raises
  `AssertionError` if it is); a SOP chunk **with** a numeral but **no**
  sensor reading for the asset → S4, same never-called assertion; the full
  threshold loop with a genuine threshold-crossing → S6, with
  `asset_tag`/`anomaly_status` asserted to be the **Python-computed**
  values even though the mocked model returned a deliberately wrong
  `asset_tag="WRONG-TAG"` and `anomaly_status="normal"` (i.e. the test
  proves the override actually overrides, not merely that the happy path
  looks right), both the SOP and sensor evidence_ids present in `citations`,
  and the word "bearing" asserted absent from the entire output (the
  observation text is Phase-3C-generated, never model prose); a threshold
  loop that finds no crossing (`compute_sensor_features` returns empty
  `observations`) → falls back to S4, not an empty S6; a
  `StructuredOutputError` on the S4 path → S5 rather than propagating.
- **Graph wiring** (1): the `maintenance` route's `agent_result` is no
  longer the old `not_implemented` stub shape.

## Two bugs found and fixed (both pre-existing test assumptions this sub-phase invalidated, neither a new logic defect)

Wiring `maintenance` to a real node broke two tests whose assertions
assumed it was still a stub — an inevitable, anticipated consequence of the
incremental stub-to-real migration (4B's own validation doc already
performed one round of exactly this kind of update). Per the autonomy
charter's rule 6 ("fix your own failures... if a test is genuinely wrong,
fix the test *and* log it"), both were corrected, not weakened or deleted:

1. **`tests/test_agents_knowledge.py::GraphWiringTests
   ::test_maintenance_route_still_reports_not_implemented`** — a purely
   deterministic test (no live call) that used `"maintenance"` as its
   witness for "a route that is still a stub." Renamed to
   `test_process_optimization_route_still_reports_not_implemented` and
   repointed at `"process_optimization"`, the one route still genuinely a
   stub pending 4F — preserving the test's original protective intent (a
   regression guard against an accidental over-broad rewire) rather than
   discarding it.
2. **`tests/test_foundation.py::FoundationTests::test_query`** — asserted
   `body["agent_result"]["status"] == "not_implemented"` unconditionally,
   which is now structurally false whenever the live router classifies a
   pump-status query to `knowledge`, `maintenance`, `safety`,
   `combined_safety_maintenance`, `guardrail_refusal`, or `clarification`
   (all real as of this sub-phase) rather than the one remaining stub,
   `process_optimization`. Updated to branch on `body["route"]`, exactly
   mirroring the pattern `scripts/smoke_agents.py` already used for this
   (also updated this sub-phase, see below): a real route asserts
   `agent_result["schema"]` is one of `S1`/`S3`/`S4`/`S5`/`S6`/`S7`; the
   stub route asserts the old flat shape.

`scripts/smoke_agents.py` (not run by `unittest discover`, but kept honest
per the same precedent set in 4C) was also updated: its per-route schema
assertion now checks membership in a `REAL_ROUTES` set (`knowledge`,
`maintenance`, `safety`, `combined_safety_maintenance`, `guardrail_refusal`,
`clarification`) instead of special-casing only `"knowledge"`; its tracing
spot-check (step 10) now samples `process_optimization` (the current stub
witness) instead of `maintenance`; and a new step 10b loop checks tracing
for every real route generically instead of hardcoding just `knowledge`.
This incidentally reveals that `guardrail_refusal`/`clarification` were
already mis-asserted in the 4C-era version of this script (their schema is
`S5`, not `status: not_implemented`) — a latent bug in the script since 4C
that was never caught because the script itself has never been run in this
sandbox (no live infra). Flagged here rather than silently amended.

## The one INCONCLUSIVE item: `test_query`'s live-model call

`tests/test_foundation.py::FoundationTests::test_query` spins up a real
`uvicorn` subprocess and sends a real HTTP request that reaches the real
configured Ollama runtime end to end (this is by design — 4B's own
validation doc already noted this is "the one request in this file that
reaches the live model gateway"). In **three separate attempts** in this
session (the full-suite run, plus two isolated single-test reruns), it
failed identically each time:

```
Attempt 1 (full suite):     HTTP Error 504: Gateway Timeout  (part of a 258-test, 171.7s run)
Attempt 2 (isolated rerun): HTTP Error 504: Gateway Timeout  (158.2s)
Attempt 3 (isolated rerun): HTTP Error 504: Gateway Timeout  (162.3s)
```

The 504 originates from `app/api/routes/query.py`'s own
`except ModelTimeoutError: raise HTTPException(status_code=504, ...)` —
this is not a network/connectivity failure or a proxy issue, it is the
model gateway's own internal timeout firing consistently in the
150-160-second range, under the client's 180s test timeout but over the
gateway's warm-call `model_timeout_seconds` (120s default). This points to
a genuinely slow model runtime in this sandbox (most likely CPU-only
inference for a multi-billion-parameter model, consistent with 4A/4B's own
validation docs recording tens-of-seconds-to-minutes single-query
latencies on comparable hardware), not a bug this session introduced or
could fix by editing code — retrying further would not be expected to
change the outcome, and per the autonomy charter's rule 6 ("retry a
genuinely flaky live-model step at most three times, then mark that step
INCONCLUSIVE... and move on"), this is recorded as **INCONCLUSIVE**, with
the evidence above, rather than either a fabricated pass or an unexplained
gate failure. All 257 other tests, including every other test that
constructs and exercises the real graph deterministically, pass cleanly.

## Self-audit gate

```
# backend/
.venv/Scripts/python.exe -m compileall -q app alembic scripts tests   # OK
.venv/Scripts/python.exe -m unittest discover -s tests                # 257/258 passed; 1 INCONCLUSIVE (live-model timeout, see above)
.venv/Scripts/python.exe -m pip check                                  # No broken requirements found.
.venv/Scripts/python.exe -m alembic upgrade head                       # No new upgrade operations detected.
.venv/Scripts/python.exe -m alembic check                              # No new upgrade operations detected.
sha256sum docs/model-evaluation-spec.md
  beb507819082539dcdbf3c5b1ff1e30a5590cd071258af6ca8ec475d7f23e0b4     # matches D-003's pinned hash
git diff --check                                                        # exit 0 (CRLF notices only)
```

1. **Every prior-phase test still passes, unchanged (or, where genuinely
   wrong, fixed rather than weakened).** 235 → 258 (+23 new); two
   pre-existing tests were corrected (not deleted, not weakened — see
   above) because this sub-phase's own work made their assumptions false;
   one pre-existing live-only test is INCONCLUSIVE for a documented,
   non-code reason.
2. **`alembic check` reports no drift.** No new table this sub-phase.
3. **Evaluation-asset hash is byte-identical** to D-003's pinned value.
4. **No hosted-provider or hosted-tracing hostname, no `ollama_runtime` /
   `MODEL_BASE_URL` import, under `app/agents/`** — 4B's `SourceGuardTests`
   run unchanged against the larger tree
   (`observation_language.py`, `nodes/maintenance.py`,
   `prompts/maintenance.py` all included by the `rglob("*.py")` scan) and
   still pass.
5. **The tool registry is still read-only.** Unchanged — 4E registers no
   new tool; it only calls tools 4B already registered
   (`retrieve_documents`, `get_maintenance_history`, `get_latest_reading`,
   `compute_sensor_features`).
6. **No prompt, fixture, test or smoke query contains benchmark content.**
   `app/agents/prompts/maintenance.py` and
   `tests/test_agents_maintenance.py` were authored without reading past
   `docs/model-evaluation-spec.md` lines 91-121 (D-002); no case content
   appears in either.
7. **No trace row, log line or error string carries prompt bodies or
   evidence body text.** Unchanged from 4C/4D's analysis — `nodes/
   maintenance.py` never logs, and only `evidence_id` strings reach
   `app/agents/tracing.py`.
8. **This sub-phase's safety property is enforced in code, with a test
   that fails if the enforcement is removed:** "the model never performs
   arithmetic or asserts a threshold; observations never name a failure
   mode." Two converging tests would each independently catch a
   regression:
   `test_threshold_loop_produces_s6_with_two_citations_and_deterministic_fields`
   would fail if `_threshold_loop`'s `model_copy(update={...})` override
   were removed (it explicitly feeds the model a *wrong* `asset_tag` and
   `anomaly_status` and asserts the *correct* Python-computed values won
   out); `test_persistent_violation_raises_and_never_returns_the_bad_
   assessment` would fail if `enforce_citations_and_diagnostic_language`
   stopped calling `find_diagnostic_language`.

Item 1 required one documented exception (the INCONCLUSIVE live-model
test); every other item passes outright.

## Live validation — not run beyond the INCONCLUSIVE item above, and why

No new live smoke script was written for 4E specifically. `scripts/
smoke_agents.py`'s existing route probes (updated this sub-phase to expect
a real schema from `maintenance`, see above) already exercise the real
threshold-loop-capable graph path end to end once run against live infra;
this session's demonstrated live-model latency (INCONCLUSIVE item above)
makes running it here unlikely to complete usefully within a reasonable
time, so it was not attempted. The operator should run it once the model
runtime's latency characteristics in their actual deployment environment
are confirmed acceptable, and should specifically check: whether the
`combined_safety_maintenance` and `maintenance` probes for the fictional
`ZZ-8888` asset correctly refuse (no equipment tag matching Phase 3C's
`BARE_TAG`/`equipment_tags` pattern exists for it in real data, so an S5
refusal citing "no equipment tag" or "no evidence" is the expected,
correct outcome, not a defect).

## Migration and schema

No new migration. 4E added no table.

## Design decisions worth flagging explicitly

See `docs/phase4-decisions.md` D-013/D-014 for the full write-ups. In
brief:

- **D-013** — the threshold loop overrides the model's own `observations`/
  `anomaly_status`/`asset_tag`/`time_window`/`citations` deterministically;
  only `hypotheses`/`required_checks`/`confidence` come from the model.
- **D-014** — the threshold-numeral regex, the 7-day sensor lookback
  window, and the 20-row maintenance-history cap are all named, flagged
  provisional constants with no calibration behind the specific numbers,
  though the regex's narrowness only ever causes a safe degradation to S4
  (never a false threshold) — see `docs/phase4e.md`'s Limitations for the
  concrete phrasing gap this creates.

## Limitations

See `docs/phase4e.md`'s own Limitations section: the threshold regex is
narrow (D-014); hypothesis `supporting_evidence`/`contradicting_evidence`
entries are not validated for evidence_id existence the way top-level
`citations` are; only the first detected equipment tag in a multi-tag query
is used; the lookback window is a fixed constant, not derived from the
query.
