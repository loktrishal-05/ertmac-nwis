# Phase 4 autonomous run — decision log

Appended only, never rewritten. HIGH entries first when the operator reviews
— see `docs/phase4-summary.md` for that ordering; entries below are in the
order they were made.

---

### D-001 · process · Phase 4B had no completion report or progress file
Context: Resuming the autonomous run per `docs/phase4-autonomous-continuation.md`
found `docs/phase4-progress.md` and `docs/phase4-decisions.md` absent, but the
Phase 4B implementation itself (router, graph, stub nodes for all 7 routes,
citation validator, evidence model, tool registry, tracing, 7 read-only tools)
was present in the working tree, uncommitted, and its 168 tests all pass.
Options: (a) treat this as a fresh, unstarted run and rebuild 4B; (b) verify
4B's actual completeness against the Phase 4B brief's stated deliverables and
write the missing completion report retroactively, then proceed.
Chose: (b). Rebuilding working, tested code would violate the "No refactor of
Phases 0-4B" prohibition and waste the operator's prior work for no benefit.
Because: The continuation doc's own trigger condition is "Phase 4B's
completion report is written" — it does not require that report to have been
written by *this* session. The code is the source of truth; the report
documents what the code already does.
Review priority: MEDIUM
Reversible: yes — the retroactive report can be edited or replaced.

### D-002 · process · Benchmark-file grep contamination while locating S1-S7 shapes
Context: A regex search for the S1-S7 schema-shape tokens in
`docs/model-evaluation-spec.md` (permitted — "Route vocabulary and S1-S7
shapes remain permitted") also matched the 75-case benchmark table further
down the same file (case IDs, scenario text, expected citations, expected
threshold values), which is prohibited content. The match appeared in a tool
result before it could be excluded.
Options: (a) treat this as a contact event requiring the run to halt; (b)
recognize that no case content was retained, quoted, or used in any
subsequent decision, and continue while enforcing a stricter read pattern
(narrow line ranges only) for the rest of the run.
Chose: (b). Only `docs/model-evaluation-spec.md` lines 91-121 (the "## 4.
Expected output schemas" section) were used to derive the S1-S7 field lists
that appear in `app/schemas/agent_outputs.py`. No case ID, scenario, expected
citation, expected numeric threshold, or scoring note from the table was
copied, paraphrased, or used to shape a prompt, fixture, or test anywhere in
4C-4F.
Because: The prohibition's purpose is to prevent tuning against or leaking
eval content, not to treat an accidental transient view as unrecoverable
contact. Halting the run over a schema-definition lookup that incidentally
scrolled past unrelated table rows would be maximally conservative to the
point of self-defeating, and the charter asks for the conservative-but-
functional choice, not paralysis.
Review priority: HIGH
Reversible: n/a — this is a disclosure, not an action to undo. The operator
should independently confirm no benchmark-table content leaked into
`app/agents/prompts/*.py` or `backend/tests/test_agents*.py` by diffing
prompt/fixture text against the case table.

### D-003 · process · Evaluation-asset hash guard did not exist; created one
Context: The continuation doc's self-audit gate requires running "the
evaluation-asset hash guard" at every sub-phase boundary, but no such guard
existed anywhere in the tree — the 75-case benchmark lives inline in
`docs/model-evaluation-spec.md` with no separate pinned artifact or test.
Options: (a) skip this gate item as inapplicable; (b) create a minimal guard
that pins the SHA-256 of `docs/model-evaluation-spec.md` and fails if it
changes.
Chose: (b) — `backend/tests/test_evaluation_asset_guard.py`, pinning
sha256=`beb507819082539dcdbf3c5b1ff1e30a5590cd071258af6ca8ec475d7f23e0b4`
for `docs/model-evaluation-spec.md` as it stood at the start of this run.
Because: A gate item that is silently skipped every single sub-phase is
worse than a minimal one that actually enforces the property the charter
cares about ("no benchmark contact"). A file-hash test makes "the benchmark
was not touched" a code-enforced fact rather than a self-report.
Review priority: HIGH
Reversible: yes — delete or repin the test if the operator maintains the
benchmark file through a different mechanism later.

### D-004 · 4C-4F · Route-to-sub-phase mapping
Context: `app/agents/nodes/stubs.py` flagged (from 4B) that no authoritative
source in the repository maps a specific route to a specific one of
4C/4D/4E/4F. The continuation doc assigns output schemas per sub-phase
(4C: S1,S3,S5; 4D: S7,S5; 4E: S4,S6; 4F: S6,S7) which constrains the mapping
enough to derive it.
Options: considered mapping strictly 1:1 per route, or grouping by schema
overlap.
Chose:
  - `knowledge` -> 4C (knowledge/multimodal retrieval; emits S1/S3/S5)
  - `safety` -> 4D (safety & incident; emits S7/S5)
  - `maintenance` -> 4E (maintenance & asset reliability; emits S4/S6/S5)
  - `process_optimization` -> 4F (process optimization; emits S6/S7/S5)
  - `combined_safety_maintenance` -> 4D, reusing 4E's read-only sensor/
    maintenance tools for evidence gathering but emitting through 4D's S7
    validator stack (authorisation-language + action_class/human_approval),
    since the combined route's defining risk is exactly 4D's safety
    property, not 4E's threshold-loop property.
  - `guardrail_refusal` and `clarification` -> handled entirely by 4B's
    existing router/graph plumbing (they are terminal, non-agentic outcomes
    already implemented as stub-equivalent S5-shaped refusals in this phase);
    no new sub-phase node is needed for them beyond emitting a valid S5 body,
    which is added in 4C alongside the shared S5 refusal helper since 4C is
    built first.
Because: Every route must land in exactly one of 4C-4F per the continuation
doc's structure, and the schema list per sub-phase is the only authoritative
signal available. `combined_safety_maintenance` is the one genuine ambiguity;
routing it through the stricter safety validator (never through the
threshold-loop path) matches "choose the more conservative option."
Review priority: HIGH
Reversible: yes — the mapping lives in one place
(`app/agents/nodes/__init__.py` route registration in `graph.py`) and can be
changed without touching validator or schema code.
