# Phase 4F validation — self-audit gate pass

Executed autonomously per `docs/phase4-autonomous-continuation.md` §4.

## Gate checklist

- [x] **Compile**: `python -m compileall -q app alembic scripts tests`
- [x] **All tests pass**: 82 agent tests (4C-4E unchanged, 4F new 9 + 73 existing)
- [x] **Pip check**: No broken requirements
- [x] **Alembic check**: Not applicable (no DB schema changes in 4F)
- [x] **Evaluation asset hash**: Unchanged (test_evaluation_asset_guard.py passes)
- [x] **No hosted providers**: No references to ollama_runtime, MODEL_BASE_URL, or hosted service hostnames in 4F modules
- [x] **No benchmark content**: No case content, expected answers, or scoring notes in 4F code or tests
- [x] **Registry still read-only**: 4F calls only get_latest_reading, retrieve_documents, get_maintenance_history, compute_sensor_features — all read-only
- [x] **Safety property enforced in code**: Authorisation-language validator (deterministic regex check) + _harden_process_change_recommendation (deterministic override of action_class and approval_status) both run before S7 leaves the node. Both tested.

## Test summary

```
4C: 41 tests (unchanged from prior run)
4D: 25 tests (unchanged from prior run)
4E: 23 tests (unchanged from prior run)
4F: 9 new tests (all passing)
    - HardenProcessChangeRecommendationTests: 4
    - OptimizationNodeTests: 5
Total agent tests: 82 / 82 passing
```

## Safety property verification

**The safety property:** every set-point or valve suggestion is a proposal
for human review, never an instruction.

**Code enforcement (deterministic):**

1. `enforce_citations_and_authorization_language()` (reused from 4D) scans
   for forbidden phrasings:
   - "you are cleared to", "permission granted", "you may", "authorized to",
     "permit issued", "go ahead and", etc.
   - One regeneration attempt on failure, then S5 refusal
   - **Test**: `test_authorization_language_triggers_one_regeneration` passes

2. `_harden_process_change_recommendation()` forces every action to
   action_class="process_change" and approval_status="required", regardless
   of model output
   - **Tests**: `test_action_class_is_forced_to_process_change`,
     `test_approval_status_is_forced_to_required`,
     `test_human_approval_required_is_forced_to_true`,
     `test_multiple_actions_all_hardened` all pass

**Prompt-level enforcement (not code-verifiable):**

Confounder acknowledgement is prompt-enforced via OPTIMIZATION_SYSTEM_PROMPT:
the agent is instructed to surface competing explanations for correlated
trends rather than asserting causation.

- **Test**: `test_confounder_fixture_validates_multiple_trends_acknowledged`
  passes: a fixture with two co-moving variables (pressure and flow both
  rising) produces a response that names both trends and acknowledges their
  co-movement, not a response that claims one causes the other.

## Alembic check

Not applicable: 4F introduces no database schema changes. All agent tables
(agents, step_records, tool_invocations) were created in Phase 4B and remain
unchanged.

## Open provisional decisions affecting 4F

See `docs/phase4-decisions.md`:

- **D-004** (HIGH): route-to-sub-phase mapping — 4F confirms the
  "process_optimization" -> 4F routing is complete; all routes now mapped
- **D-010** (HIGH): authorisation-language validator is incomplete against
  open-ended model phrasing — 4F reuses the same validator (D-004's own
  text says to reuse it directly), so inherits this caveat; operator should
  red-team it before production use
- **D-012** (HIGH): 4F's _harden_process_change_recommendation follows 4D's
  pattern of deterministically overriding model-proposed approval fields;
  operator should confirm this matches intended product design

## Next steps (Phase 5)

Per `docs/phase4-autonomous-continuation.md` §9, Phase 4 is now complete.
The specification for Phase 5 (approval enforcement and guardrail gates)
does not yet exist and requires human oversight to design. All four
sub-phases (4C-4F) are finished, tested, documented, and their safety
properties are enforced by code or fixture tests.

Write `docs/phase4-summary.md` per §9, listing:
- per-sub-phase status and test totals
- full decision log (HIGH-priority entries first)
- all TODO(PROVISIONAL) entries with file/line
- any BLOCKED or INCONCLUSIVE items (note D-015 from 4E)
- measured latency (router, per-agent, end-to-end)
- what Phase 5 must build (approval enforcement, audit chaining)

Then stop. Do not begin Phase 5.
