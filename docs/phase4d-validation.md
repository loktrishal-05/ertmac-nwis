# Phase 4D — Validation

## Deterministic backend tests

```
# backend/
.venv/Scripts/python.exe -m unittest discover -s tests
...
Ran 235 tests in 33.283s
OK
```

235 tests total, all passing. Before this sub-phase the suite stood at 210
(4C's own count); the delta is **+25**, entirely new coverage
(`tests/test_agents_safety.py`), zero modifications to any test file that
existed before this sub-phase.

- **`safety_language.py`** (8): clean procedure-citation text is never
  flagged; each of the six seed phrasing categories ("you are cleared to",
  "permission granted", "you may now isolate", "authorised to", "permit
  issued", "go ahead and...") is individually asserted flagged; a sentence
  that *reports a procedural requirement* ("a permit must be obtained
  before...") is explicitly asserted **not** flagged — the negative-
  lookahead exception is tested, not just the positive matches.
- **`enforce_citations_and_authorization_language()`** (3): valid on the
  first attempt with no retry; a language-only violation uses exactly one
  regeneration, with the retry note containing the word "authoris..." (the
  citation check silently passes throughout); a citation-and-language
  double failure after `max_attempts` raises `EnforcementFailure` whose
  `missing_evidence` contains the unknown id and whose `reason` contains
  "authorisation-implying" — and, per the fix described below,
  contains neither the rejected sentence nor a raw regex source string.
- **`_harden_action_recommendation()`** (5): a model-claimed
  `approval_status="approved"` is downgraded to `"required"`
  unconditionally; a non-informational action forces
  `human_approval_required=True` at the top level even when the model set
  it `False`; a purely informational action is left untouched (no spurious
  escalation); `_dominant_action_class` picks the single most severe class
  present (`shutdown` over `inspection` over `informational`, tested with
  all three in one recommendation); returns `None` when there are no
  proposed actions at all.
- **`safety_node()`** (7): no evidence → S5 directing to human escalation,
  language asserted to contain "Escalate"; a valid recommendation → S7,
  with `human_approval_required`/`action_class` correctly propagated to
  `WorkbenchState` top-level fields (not just inside `agent_result`); a
  model-claimed self-approval is overridden before the node returns (the
  *node-level* integration test, complementing the unit-level
  `_harden_action_recommendation` tests above); a persistent
  authorisation-language violation → S5, gateway called exactly twice, and
  the word "cleared" (from the rejected sentence) is asserted **absent**
  from the entire returned `agent_result`; a `StructuredOutputError` → S5
  rather than propagating; the `combined_safety_maintenance` route is
  asserted to call exactly `{retrieve_documents, get_maintenance_history,
  get_latest_reading}` for a query naming `P-204`, with all 3 evidence refs
  present in the returned state; the plain `safety` route is asserted to
  call `retrieve_documents` **only** — `mocked.assert_called_once()` — even
  when the same equipment-tag-bearing query text is used, proving the tool
  gating is keyed on `route`, not on query content.
- **Graph wiring** (2): both `safety` and `combined_safety_maintenance`
  routes produce a schema-valid `S5` (not the old `not_implemented` stub
  shape) through the fully compiled graph.

## A test-scoping bug found and fixed during this sub-phase (not a product bug)

While writing `SafetyGraphWiringTests`, the graph-invocation call was
initially placed *outside* the `with patch(...)` context manager that
mocked `app.agents.nodes.safety.invoke_tool` — a mistake, since `gateway`
is captured by closure at `build_graph()` time (so a `get_model_gateway`
patch only needs to be active during the build call), but `invoke_tool` is
looked up by name at call time inside the node body, during
`graph.invoke()`, which is too late if the patch has already been
reverted. The **same bug was present, already committed, in 4C's own**
`tests/test_agents_knowledge.py::GraphWiringTests
::test_knowledge_route_no_longer_reports_not_implemented`
— it happened to still pass, because this sandbox's local Qdrant and
embedding model turned out to be reachable, and a `MagicMock` session's
default (empty) `__iter__` behaviour, propagated into
`retrieve()`'s document-version-id filter, coincidentally produced a
zero-result real search. That is a fragile pass for the wrong reason, not
a verified one, and running a live retrieval pipeline (visible as
"Loading weights" progress-bar noise in the earlier 4C-only test run) is
exactly the kind of unrecorded live dependency the deterministic suite is
supposed to avoid. Both files were fixed in this sub-phase — the `graph
.invoke()` call moved inside the `with` block in both — and the full suite
was re-run to confirm: no more model-loading side effects, `51` of the
combined 4C+4D node/graph-wiring tests complete in `0.074s` (previously
tens of seconds with live inference), and all assertions still hold. This
is logged here rather than silently amended, per the autonomy charter's
rule 6 ("fix your own failures... never delete or weaken a test to make it
pass; if a test is genuinely wrong, fix the test *and* log it").

## Self-audit gate

```
# backend/
.venv/Scripts/python.exe -m compileall -q app alembic scripts tests   # OK
.venv/Scripts/python.exe -m unittest discover -s tests                # 235 passed
.venv/Scripts/python.exe -m pip check                                  # No broken requirements found.
.venv/Scripts/python.exe -m alembic upgrade head                       # No new upgrade operations detected.
.venv/Scripts/python.exe -m alembic check                              # No new upgrade operations detected.
sha256sum docs/model-evaluation-spec.md
  beb507819082539dcdbf3c5b1ff1e30a5590cd071258af6ca8ec475d7f23e0b4     # matches D-003's pinned hash
git diff --check                                                        # exit 0 (CRLF notices only)
```

1. **Every prior-phase test still passes, unchanged.** 210 → 235 (+25); the
   two pre-existing test files touched this sub-phase
   (`tests/test_agents_knowledge.py`) had only the scoping-bug fix above
   applied to their own not-yet-independently-reviewed 4C test, not a
   weakening — the assertions inside that test are unchanged, only which
   patches are active while it runs.
2. **`alembic check` reports no drift.** No new table this sub-phase.
3. **Evaluation-asset hash is byte-identical** to D-003's pinned value.
4. **No hosted-provider or hosted-tracing hostname, no `ollama_runtime` /
   `MODEL_BASE_URL` import, under `app/agents/`** — 4B's `SourceGuardTests`
   run unchanged against the larger tree (`safety_language.py`,
   `nodes/safety.py`, `prompts/safety.py`, `prompts/shared.py` all included
   by the `rglob("*.py")` scan) and still pass.
5. **The tool registry is still read-only.** Unchanged — 4D registers no
   new tool; it only calls three tools 4B already registered
   (`retrieve_documents`, `get_maintenance_history`, `get_latest_reading`).
6. **No prompt, fixture, test or smoke query contains benchmark content.**
   `app/agents/prompts/safety.py` and `tests/test_agents_safety.py` were
   authored without reading past `docs/model-evaluation-spec.md` lines
   91-121 (D-002); no case content appears in either.
7. **No trace row, log line or error string carries prompt bodies or
   evidence body text.** Unchanged from 4C's analysis — `nodes/safety.py`
   never logs, and only `evidence_id` strings reach `app/agents/tracing.py`.
8. **This sub-phase's safety property is enforced in code, with a test that
   fails if the enforcement is removed:** "no output ever reads as
   authorisation to act." Three converging tests would each independently
   catch a regression: `test_you_are_cleared_to_is_flagged` (et al.) would
   fail if a pattern were removed from `safety_language.py`;
   `test_persistent_authorization_language_refuses_never_ships_the_recommendation`
   would fail if `enforce_citations_and_authorization_language` stopped
   calling `find_authorization_language`; and
   `test_model_self_approval_is_overridden_before_leaving_the_node` would
   fail if `_harden_action_recommendation` were removed or weakened to pass
   `approval_status="approved"` through unchanged.

All eight items pass; none required a `BLOCKED` entry.

## Live validation — not run, and why

No live smoke script was extended for 4D in this session (the 4C brief's
own smoke items were the ones the continuation doc names explicitly; 4D
adds no separate live-smoke requirement beyond `scripts/smoke_agents.py`'s
existing `safety`/`combined_safety_maintenance` route probes, which already
exercise the real graph end-to-end and would now hit `safety_node` instead
of the stub). As with 4C, this session has no reachable local Ollama,
Postgres, or Qdrant to run it against, so — per the autonomy charter's rule
7 — this is recorded as **NOT RUN**, not as a passing number. The operator
should run `scripts/smoke_agents.py` and specifically check: the
`safety`/`combined_safety_maintenance` probes' `agent_result.schema` (an S5
refusal is expected and correct for the fictional `ZZ-8888` asset, which
has no indexed SOP/incident/maintenance evidence — the same
no-evidence path `test_no_evidence_refuses_and_directs_to_human_escalation`
exercises deterministically), and, if any real SOP/incident content is
indexed in a non-synthetic environment, that a genuinely action-adjacent
recommendation is phrased as this document describes rather than as an
instruction — something only a live model call can confirm.

## Migration and schema

No new migration. 4D added no table.

## Design decisions worth flagging explicitly

See `docs/phase4-decisions.md` D-010 through D-012 for the full write-ups.
In brief:

- **D-010** — the authorisation-language pattern list is broader than the
  brief's four literal example phrasings, and is explicitly a floor, not a
  ceiling, pending Phase 5's real approval gate.
- **D-011** — `combined_safety_maintenance`'s equipment-tag detection is
  deterministic (regex-based), not model-inferred, capped at 3 tags.
- **D-012** — the node overrides the model's `approval_status`/
  `human_approval_required` values deterministically; this is recording
  accurately, not the approval enforcement Phase 5 owns, but the operator
  should re-confirm this framing before Phase 5 is built on top of it.

## Limitations

See `docs/phase4d.md`'s own Limitations section: the authorisation-language
list cannot be exhaustive; S7 has no dedicated `severity` field to
code-enforce escalation against (prompt-level only); tag detection for
`combined_safety_maintenance` is regex-based and degrades safely (not
silently) to plain-`safety` behaviour when no recognizable tag is present.
