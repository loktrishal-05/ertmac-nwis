# Phase 4C — Validation

## Deterministic backend tests

```
# backend/
.venv/Scripts/python.exe -m unittest discover -s tests
...
Ran 210 tests in 75.614s
OK
```

210 tests total, all passing. Before this sub-phase the suite stood at 169
(4B's own count); the delta is **+41**, entirely new coverage, zero
modifications to any pre-existing test file — `tests/test_agents.py` (4B)
is untouched.

New files:

- `tests/test_agent_outputs.py` (18 tests): `extra="forbid"` on
  `GroundedAnswer`/`Refusal`/`EquipmentTag`/`ActionRecommendation`;
  `Refusal.status` and `EquipmentTag.status` and `ProposedAction.action_class`
  are closed enums; `MaintenanceHypothesis` structurally rejects a hypothesis
  with neither `supporting_evidence` nor `contradicting_evidence`, and
  accepts either alone; confidence bounds enforced on `GroundedAnswer`;
  `SensorObservation` requires `evidence_id`.
- `tests/test_agents_knowledge.py` (23 tests):
  - **`refuse()`** (2): never calls a model, builds a valid S5; an unknown
    `status` value raises `ValidationError` (the enum is closed).
  - **`enforce_citations()`** (3): a valid citation on the first attempt
    returns immediately with no retry; an invalid-then-valid sequence uses
    exactly one regeneration carrying the validator's own unknown-id list in
    the retry note; a persistently-invalid sequence raises
    `CitationEnforcementFailure` after exactly `max_attempts` calls, with the
    unknown id present in the refusal's `missing_evidence`.
  - **`_assess_evidence()`** (4): empty results insufficient; below-floor
    insufficient; an identifier-miss warning refuses **even when the top
    score is deliberately set far above the floor** (the D-007 conservative
    reading, tested explicitly so a future edit that only checks the floor
    would fail this test); above-floor with no identifier-miss is
    sufficient.
  - **`knowledge_node()`** (9): no evidence → S5 with empty evidence list;
    below floor → S5 **without calling the gateway at all**
    (`gateway.generate_structured.assert_not_called()`); a valid grounded
    answer → S1 with the citation's `evidence_id` intact; a persistently
    invalid citation → S5, gateway called exactly twice (one regeneration),
    and the fabricated answer text is asserted **absent** from the returned
    `agent_result` entirely; a `StructuredOutputError` from the gateway → S5
    rather than propagating; OCR evidence at `ocr_confidence=0.99` with no
    registry match → status stays `unverified`, **never** `verified`; the
    same evidence with a registry match → `verified`; an injected
    instruction embedded in retrieved text is asserted present inside the
    `<evidence id="...">` block of the **user** message and absent from the
    **system** message — the strongest test this suite can run for prompt
    injection without a live model, since actually verifying the model
    *complies* with the framing needs a live smoke (see below).
  - **Prompt module** (3): system prompt names evidence blocks "QUOTED DATA"
    and "not instructions"; `format_evidence_block` produces a delimited,
    labelled block; an empty evidence list is reported as absent explicitly
    in the user message rather than silently rendered as blank.
  - **Terminal nodes** (3): `guardrail_refusal_node` emits S5
    `status="refused"` carrying the router's own reasoning;
    `clarification_node` emits S5 `status="clarification_required"`; both
    tolerate a missing `route_reasoning` key without raising.
  - **Graph wiring** (3): the `knowledge` route's `agent_result` is no
    longer the old `{"status": "not_implemented", ...}` stub shape (asserted
    by its *absence*); `guardrail_refusal` now returns a schema-valid S5
    through the full compiled graph; `maintenance` (still a 4B stub, pending
    4D) is asserted **unchanged** — this is the regression guard that would
    catch an accidental over-broad rewire.

## Self-audit gate

```
# backend/
.venv/Scripts/python.exe -m compileall -q app alembic scripts tests   # COMPILE_OK
.venv/Scripts/python.exe -m unittest discover -s tests                # 210 passed
.venv/Scripts/python.exe -m pip check                                  # No broken requirements found.
.venv/Scripts/python.exe -m alembic upgrade head                       # No new upgrade operations detected.
.venv/Scripts/python.exe -m alembic check                              # No new upgrade operations detected.
sha256sum docs/model-evaluation-spec.md
  beb507819082539dcdbf3c5b1ff1e30a5590cd071258af6ca8ec475d7f23e0b4     # matches D-003's pinned hash
git diff --check                                                        # exit 0 (CRLF notices only, no errors)
```

1. **Every prior-phase test still passes, unchanged.** 169 → 210 (+41), no
   modification to any test file that existed before this sub-phase.
2. **`alembic check` reports no drift.** No migration touched this
   sub-phase — 4C is agent/prompt/schema code only, no new table.
3. **Evaluation-asset hash is byte-identical** to D-003's pinned value.
4. **No hosted-provider or hosted-tracing hostname, no `ollama_runtime` /
   `MODEL_BASE_URL` import, under `app/agents/`** — covered by 4B's own
   `SourceGuardTests`, which run unchanged against the now-larger
   `app/agents/` tree (`nodes/knowledge.py`, `nodes/terminal.py`,
   `enforcement.py`, `prompts/knowledge.py` are all included by the test's
   `rglob("*.py")` scan) and still pass.
5. **The tool registry is still read-only.** Unchanged — 4C registers no
   new tool; `RegistryTests.test_all_seven_tools_registered_exactly_once`
   still asserts exactly the same seven names.
6. **No prompt, fixture, test or smoke query contains benchmark content.**
   `app/agents/prompts/knowledge.py` and `tests/test_agents_knowledge.py`
   were authored without reading past `docs/model-evaluation-spec.md` lines
   91-121 (see D-002); no case ID, scenario text, or expected answer from
   that file's case table appears in either.
7. **No trace row, log line or error string carries prompt bodies or
   evidence body text.** `nodes/knowledge.py` never logs; the only values
   written into `WorkbenchState["evidence"]` are `EvidenceRef` objects
   (already covered by 4B's tracing contract, which persists only
   `evidence_id` strings — see `app/agents/tracing.py`); `agent_result`
   itself (which does carry the model's answer text) is returned to the
   caller in `POST /query`'s response body as designed, not written to a
   log.
8. **This sub-phase's safety property is enforced in code, with a test that
   fails if the enforcement is removed:** "an answer containing a citation
   that was not in the evidence gathered for that turn never leaves the
   node." Enforced by `enforce_citations()` +
   `test_persistently_invalid_citation_refuses_and_never_ships_the_answer`,
   which asserts both that the schema is `S5` (not `S1`) and that the
   fabricated answer text does not appear anywhere in the returned
   `agent_result` — a regression that stripped the bad citation and shipped
   the answer anyway (the exact failure mode the 4C brief calls out by
   name) would fail this test on the "schema == S5" assertion alone.

All eight items pass; none required a `BLOCKED` entry.

## Live validation — not run, and why

`scripts/smoke_agents.py` was extended (schema-valid assertion on the
`knowledge` route's real output; a new step 10b tracing check) but **not
executed** in this session: it requires a reachable local Ollama runtime,
Postgres, and Qdrant, none of which this sandboxed session has running
(the deterministic suite above uses a MagicMock gateway and, for the two
tests that touch a real service singleton indirectly through import — see
below — a real local reranker/embedding model already resident in
`models/`, not a network call). Per the autonomy charter's rule 7 ("never
fabricate a result"), this is recorded as **NOT RUN**, not as a passing
number. The operator should run:

```
# backend/
.venv/Scripts/python.exe -m scripts.smoke_agents
```

and would want to specifically confirm: the `knowledge` route's live
`agent_result.schema` for the `ZZ-8888` probe (an `S5` refusal is expected
and correct, since `ZZ-8888` is a fictional asset with no indexed
evidence — this is the same identifier-miss path
`test_no_evidence_produces_s5_refusal_not_an_answer` exercises
deterministically); and that the prompt-injection framing actually holds
against the live model (the deterministic suite proves the *code path*
keeps injected text inside a data block and out of the system prompt, but
only a live model call can confirm the model itself does not comply with
it).

## Migration and schema

No new migration. 4C added no table, and `alembic check` above confirms no
drift was introduced by any model import.

## Design decisions worth flagging explicitly

See `docs/phase4-decisions.md` D-005 through D-009 for the full write-ups.
In brief:

- **D-005** — S1-S7 are defined once in `app/schemas/agent_outputs.py`
  rather than per sub-phase.
- **D-006** — every S5 `Refusal` in 4C-4F is built in Python, never through
  the model gateway.
- **D-007** — the evidence-sufficiency check refuses on an identifier-miss
  warning regardless of score, not only when the score is also low.
- **D-008** — `build_graph(session=...)` / `run_graph(session=...)`:
  session-bound nodes get a freshly-built graph per request rather than
  reusing 4B's cached singleton, which cannot hold a request-scoped
  dependency.
- **D-009** — `KNOWLEDGE_RELEVANCE_FLOOR` default of `0.0` is provisional;
  Phase 3B2 explicitly found no calibrated threshold to inherit.

## Limitations

See `docs/phase4c.md`'s own Limitations section: `get_pid_regions` is not
called by this node; `equipment_type`/`normalized_tag` on S3 output are
never model-inferred, only normalized; no multi-turn, streaming, or
checkpointer support (unchanged from 4B's scope).
