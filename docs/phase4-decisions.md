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

### D-005 · 4C · S1-S7 defined once in app/schemas/agent_outputs.py, not per sub-phase
Context: Each of 4C-4F could define its own output schema(s) locally (e.g.
`app/agents/nodes/knowledge.py` defining its own `GroundedAnswer`), or all
seven could be defined once in a shared module read while deriving the
field lists from `docs/model-evaluation-spec.md` lines 91-121 (see D-002).
Options: (a) one schema module per sub-phase, each independently reading the
spec section relevant to its own routes; (b) one shared module,
`app/schemas/agent_outputs.py`, defining all of S1-S7 up front, imported by
every later sub-phase.
Chose: (b).
Because: Schemas are reused across sub-phases (S5 by every route; S6 by both
4E and 4F; `MaintenanceHypothesis` by both S4 and S6), so per-sub-phase
definitions would either duplicate the shape or force 4D-4F to import from
4C's node module — a layering inversion (a node module is not a schema
module). A single shared module also means the benchmark-spec section
(lines 91-121) is read exactly once across the whole autonomous run, which
minimizes the surface for the exact kind of incidental over-read D-002
already had to account for. This module was written before this session
began (see the file's own header) as unit 1 of 4C's six units; this entry
records the decision it presupposed but that had not yet been logged.
Review priority: MEDIUM
Reversible: yes — splitting per sub-phase later would touch only import
statements, not field shapes, since every consumer already imports by name.

### D-006 · 4C · Every S5 Refusal is built in Python, never through the model gateway
Context: The 4C brief's shared S5 refusal helper could plausibly go either
way: phrase refusals via `generate_structured` (consistent with "S1/S3/S5
emission through generate_structured" in the brief's item 5), or build them
deterministically from information the calling code already has (a tool
result, a citation-validator error, the router's own `route_reasoning`).
Options: (a) always call the model to phrase a refusal's `reason` and
`safe_next_step`; (b) build every S5 body in pure Python via a shared
`refuse()` helper, calling the model never.
Chose: (b) — `app/agents/enforcement.py::refuse()`. Used by
`nodes/knowledge.py`'s insufficient-evidence and citation-failure paths, and
by the new `nodes/terminal.py::guardrail_refusal_node` /
`clarification_node`.
Because: A refusal is inherently a security/trust-relevant utterance — it is
the system telling the operator "I did not do X, here is why." Every input
to that message is already known deterministically by the calling code
(what was searched for, what the validator rejected, why the router
classified as it did); asking the model to phrase it adds a hallucination
surface to the one output type where fabrication is least acceptable, for a
purely stylistic benefit. This is the conservative reading of an ambiguous
brief item, consistent with the autonomy charter's rule 3.
Review priority: MEDIUM
Reversible: yes — `refuse()` is a single call site per caller; routing it
through `generate_structured` instead would not change any schema.

### D-007 · 4C · Identifier-miss refuses regardless of score, not only jointly with a low score
Context: The 4C brief's evidence-sufficiency check says: "Below the floor,
or on an identifier miss with no supporting hit, the agent refuses." Read
literally, "no supporting hit" could just mean "below the floor" again,
collapsing the whole sentence to a single below-floor check with
identifier-miss as decorative context. A second reading treats
identifier-miss as an independent, unconditional refusal trigger.
Options: (a) refuse only when `top_score < floor` (identifier-miss only
shapes the refusal *message*, not the decision); (b) refuse when
`top_score < floor` **or** when an identifier-miss warning is present at
all, regardless of score.
Chose: (b) — `app/agents/nodes/knowledge.py::_assess_evidence()`.
Because: Phase 3B2 (`docs/phase3b2-validation.md`) measured dense and hybrid
retrieval returning unrelated neighbours for a nonexistent identifier
(`ZZQ-99999`) with no calibrated rejection threshold available (that file's
own words: "There is no calibrated rejection threshold"). Under reading (a),
an operator who raises `KNOWLEDGE_RELEVANCE_FLOOR` to reduce false refusals
would simultaneously reopen exactly the failure mode 3B2 flagged — an
unrelated neighbour scoring adequately for a genuinely missing identifier.
Reading (b) keeps that specific failure mode closed independent of how the
floor is tuned, matching "choose the more conservative option."
Review priority: HIGH
Reversible: yes — single boolean condition in `_assess_evidence()`; changing
`or` to `and` reverts to reading (a). Flagged HIGH because it materially
changes how often the knowledge agent refuses on real traffic, which the
operator should confirm matches their tolerance.

### D-008 · 4C · Session-scoped nodes bypass the 4B cached-graph singleton
Context: 4B's `get_graph()` is an `lru_cache(maxsize=1)` singleton because
its only stateful per-node dependency, the model gateway, is itself a
process-wide singleton (`get_model_gateway()`). Phase 4C's `knowledge_node`
needs a SQLAlchemy `Session` to call `retrieve_documents` and to look up the
equipment registry — and a `Session` is request-scoped, not process-scoped,
so it cannot be baked into a cached compiled graph the same way.
Options: (a) restructure the graph to thread a session through LangGraph's
`config`/`context` mechanism on every invocation, keeping one cached
compiled graph; (b) give `build_graph()` an optional `session=None`
parameter, bind session-needing nodes to it by closure (mirroring 4B's own
`router_node`/gateway closure pattern exactly), and have `run_graph()` build
a fresh graph per call whenever a real session is supplied, falling back to
the existing cached singleton when it is not.
Chose: (b).
Because: (a) is more "elegant" but depends on LangGraph 1.2's `Runtime`/
`context` API working exactly as documented for this project's specific
node-function calling convention, which this session could not fully verify
against a live LangGraph without risking a broken graph under autonomy with
no one to notice. (b) reuses a pattern 4B already validated (closures for
process-wide singletons), needed zero changes to `_traced()` or any existing
node's signature, and every pre-existing 4B test (which calls
`build_graph()`/`get_graph()` with no session) continues to pass byte-for-
byte unchanged. The cost is that a real `/query` request no longer benefits
from the cached compiled graph (it rebuilds `StateGraph.compile()` per
request); this is expected to be negligible next to local-model inference
latency (tens of seconds per 4B's own validation doc) but is not measured
live in this session — see `docs/phase4c-validation.md`.
Review priority: MEDIUM
Reversible: yes — swapping to config/context-based session threading later
would only touch `graph.py` and `run_graph()`'s call sites, not node bodies.

### D-009 · 4C · KNOWLEDGE_RELEVANCE_FLOOR default of 0.0 is a provisional, uncalibrated number
Context: The 4C brief requires "a relevance floor the agent applies itself
(`KNOWLEDGE_RELEVANCE_FLOOR`, configurable, conservative default)" but no
calibrated value exists anywhere in the repository — `docs/phase3b2-
validation.md` states outright "There is no calibrated rejection
threshold," and `RetrievedChunk.score` is, under the default
`hybrid_rerank` strategy, a raw cross-encoder logit
(`app/services/reranking.py`: "scores are raw logits, never
probabilities"), not a bounded 0-1 relevance probability.
Options: (a) pick an arbitrary bounded-looking default (e.g. 0.5) that would
be meaningless against an unbounded logit scale; (b) default to `0.0`, the
cross-encoder's own zero-crossing (its training objective makes a
non-negative logit a non-negative relevance signal), and document loudly
that this is uncalibrated; (c) leave the floor unset/`None` and skip the
score check entirely, relying only on the identifier-miss signal and an
empty-result check.
Chose: (b).
Because: (c) would silently drop half of the brief's required "combining"
check (see D-007) whenever the identifier-miss warning does not fire — e.g.
a query with no technical identifier at all that still returns garbage
low-relevance chunks. (a) would be actively misleading (a bounded-looking
number on an unbounded scale invites an operator to reason about it as if
it were a probability). (b) is at least *interpretable* against the
reranker's own semantics, is fully operator-tunable via
`WORKBENCH_KNOWLEDGE_RELEVANCE_FLOOR`, and is loudly marked provisional in
three places: this entry, `config.py`'s inline comment, and
`docs/phase4c.md`.
Review priority: HIGH — this is a product-behavior-shaping number with no
empirical backing yet; the operator should tune it against real retrieval
traffic before relying on it in production.
Reversible: yes — a single `Field(default=...)` in `app/core/config.py`.

### D-010 · 4D · The authorisation-language validator is a fixed regex list, not exhaustive
Context: The 4D brief requires "a deterministic authorisation-language
validator over the output — a forbidden-construction check for phrasings
like 'you are cleared to', 'permission granted', 'you may now isolate',
'authorised to'". No canonical phrase list exists anywhere in the
repository or spec to import; one had to be authored.
Options: (a) a short list matching only the brief's own four example
phrasings verbatim; (b) a broader list covering the same four semantic
categories (clearance, permission, permit issuance, "go ahead") with a
handful of phrasings each, plus a narrow negative-lookahead so "authorised
to request/obtain/seek [a permit]" — which reports a requirement, not a
grant — is not falsely flagged.
Chose: (b) — `app/agents/safety_language.py`.
Because: (a) would satisfy the brief's literal text but miss trivial
paraphrases (e.g. "you're cleared for entry", "the permit has been
issued") that carry the identical risk the property exists to prevent; a
regex list can never be exhaustive against open-ended model phrasing, but a
broader deterministic net is more conservative than a narrower one, and (as
`enforce_citations_and_authorization_language` shows) a false positive here
only costs one bounded regeneration, not an incorrect refusal — a false
negative is the more dangerous failure mode by far.
Review priority: HIGH — this list is the entire enforcement mechanism for
4D's stated safety property; the operator should red-team it with
paraphrases the four seed phrasings do not cover (regional phrasing,
non-English-influenced English, abbreviations) before relying on it as a
sole safeguard, and should treat it as a floor, not a ceiling — Phase 5's
actual approval gate is the real control, per the continuation doc's own
framing that 4C-4F only *record* `human_approval_required`.
Reversible: yes — `_FORBIDDEN_PATTERNS` is one list in one module, shared by
4D and 4F per the brief's explicit reuse instruction.

### D-011 · 4D · combined_safety_maintenance equipment-tag detection is deterministic, capped at 3 tags
Context: `combined_safety_maintenance` (D-004) needs to pull maintenance/
sensor evidence for whatever equipment the query concerns, but the query is
free text — nothing hands the node a structured `equipment_tag`.
Options: (a) ask the model, in a separate structured call, to extract the
equipment tag(s) from the query before gathering evidence; (b) reuse the
existing deterministic identifier extractor
(`app.services.sparse.identifiers`, already used by `retrieval.py`'s own
identifier-miss check) to find tag-shaped substrings in the query text
directly, with no model call, capped at the first 3 distinct tags found.
Chose: (b) — `app/agents/nodes/safety.py::_gather_evidence`.
Because: (a) adds a model call (latency, and a second surface for the model
to hallucinate a tag that does not exist) to what is fundamentally a
pattern-matching problem the codebase already solves deterministically
elsewhere. The cap of 3 exists to bound the number of tool calls a single
turn can trigger — consistent with the project's existing bounded-window/
bounded-limit discipline (`app/agents/tools/base.py`) — and is itself a
provisional number with no calibration behind it beyond "small and
finite."
Review priority: MEDIUM
Reversible: yes — `_MAX_COMBINED_TAGS` is one module-level constant.

### D-012 · 4D · The node overrides the model's approval_status/human_approval_required, not just validates them
Context: The 4D brief requires `action_class` and `human_approval_required`
"recorded as fields" on every action-adjacent proposal, and separately that
4D "must not gate" — approval *enforcement* is explicitly Phase 5's job
(continuation doc section 2's prohibition list). It was ambiguous whether
`_harden_action_recommendation` correcting the model's own
`approval_status`/`human_approval_required` values crosses into
"enforcement."
Options: (a) pass the model's `approval_status`/`human_approval_required`
values through unmodified, only validating the *shape* (schema-level enum
membership, already covered) — treat any semantic wrongness as the model's
problem to fix via the citation/language regeneration loop only; (b)
deterministically override `approval_status="approved"` to `"required"`
unconditionally, and force `human_approval_required=True` whenever any
proposed action's `action_class` is not `"informational"`, regardless of
what the model set.
Chose: (b).
Because: This is *recording accurately*, not *enforcing a gate* — the
distinction the prohibition draws is about whether the system BLOCKS an
output pending approval (it does not: 4D always returns a result, S7 or
S5, synchronously, same as every other sub-phase), not about whether the
recorded fields are trustworthy. A model that emits
`approval_status="approved"` on its own output would otherwise let the
*record itself* claim an approval that never happened — precisely the
"reads as authorisation" failure mode 4D's safety property exists to
prevent, just relocated from prose into a structured field a future Phase 5
gate might trust naively. Overriding it in code makes "this system never
self-approves" a code-enforced fact rather than a prompt instruction (the
same reasoning D-006/D-007 already applied to language and evidence).
Review priority: HIGH — this is exactly the kind of decision the operator
should re-derive independently before Phase 5 is built, since Phase 5's
approval gate will presumably trust `approval_status`/`human_approval_required`
as ground truth; confirm this override matches that future design.
Reversible: yes — `_harden_action_recommendation` is one function in
`app/agents/nodes/safety.py`.

### D-013 · 4E · The threshold loop bypasses the model entirely for observations/anomaly_status
Context: The 4E brief's threshold loop describes the model "locating the
limit in cited text" and Python doing the extraction/comparison, but leaves
open how much of the FINAL S6 output the model is allowed to author once
that comparison is done.
Options: (a) let the model see the deterministic observations and author
the entire `SensorInterpretation` object, including `observations`,
`anomaly_status`, `asset_tag`, `time_window`, and `citations`, trusting it
to transcribe them faithfully; (b) let the model author only the
interpretive fields (`hypotheses`, `required_checks`, `confidence`) and
deterministically overwrite `observations`/`anomaly_status`/`asset_tag`/
`time_window`/`citations` with the Python-computed values regardless of
what the model returned.
Chose: (b) — `app/agents/nodes/maintenance.py::_threshold_loop`.
Because: 4E's stated safety property is "the model never performs
arithmetic or asserts a threshold." A model that transcribes a Python-
computed observation is still, structurally, the thing whose output decides
what the operator reads as the observation — a transcription error
(dropping a threshold-exceeded finding, softening "exceeded" to "near") is
indistinguishable downstream from the model asserting the threshold itself.
Overwriting these fields in code makes "the model did not decide this"
verifiable by reading `nodes/maintenance.py`, not merely likely by reading
a prompt. This mirrors D-012's identical reasoning for 4D.
Review priority: MEDIUM
Reversible: yes — the `model_copy(update={...})` call is one block; removing
it reverts to trusting the model's own transcription.

### D-014 · 4E · Threshold-numeral regex, lookback window, and history-row cap are all provisional constants
Context: Three numbers had no source to derive from: (1) the deterministic
regex pattern used to locate a numeral near a limit-keyword in SOP text
(`_THRESHOLD_PATTERN`); (2) how far back to query sensor readings once a
threshold is found, since the query text carries no explicit time range
(`_THRESHOLD_WINDOW_DAYS`); (3) how many maintenance-history rows to pull
per turn (`_MAX_HISTORY_ROWS`).
Options considered: for the regex, a wider character gap between keyword
and numeral (more recall, more risk of grabbing an unrelated number) versus
a narrower one (current choice: keyword, then up to 15 non-digit
characters, then the numeral) — chosen for keeping the numeral tightly
scoped to the keyword that licenses it, since a threshold extracted from
the wrong sentence is exactly the "asserts a threshold" failure mode this
sub-phase exists to prevent, just moved into the regex instead of the
model. For the window, 7 days was chosen as a small, human-legible default
consistent with the "bounded" instruction in the brief's item 4, with no
calibration behind the specific number 7. For the row cap, `20` matches the
existing default `limit` on `GetMaintenanceHistoryArguments`
(`app/agents/tools/maintenance.py`), reusing an existing convention rather
than inventing a new one.
Chose: as implemented; all three are named module-level constants, not
buried literals.
Because: each is a defensible, bounded default with an honest paper trail,
not a guess dressed up as a calibrated number — consistent with the
project's standing preference (see D-009) for provisional-but-flagged over
silently invented.
Review priority: MEDIUM — none of these gate a safety property directly
(the threshold VALUE always comes from cited text, never from these
constants); they shape recall/coverage, not correctness. The operator
should tune `_THRESHOLD_WINDOW_DAYS` in particular once real SOP phrasing
conventions are known, since a real limit written as "maximum permissible
value of X" would currently slip past the 15-character gap and fall
through to the S4 general-assessment path instead of the threshold loop —
a safe degradation (never a false threshold), but a missed one.
Reversible: yes — three named constants in `app/agents/nodes/maintenance.py`.

### D-015 · 4E · test_query's live-model call marked INCONCLUSIVE after three attempts; two stale test assumptions fixed
Context: Running the self-audit gate's `unittest discover` after wiring
`maintenance` to a real node surfaced two failures. One,
`test_agents_knowledge.py::GraphWiringTests
::test_maintenance_route_still_reports_not_implemented`, was a
deterministic logic bug: it hardcoded `"maintenance"` as its witness for "a
route that is still a stub," which this sub-phase's own work made false.
The other, `test_foundation.py::FoundationTests::test_query`, asserted the
same now-false stub-shape unconditionally, AND depends on a real live
Ollama call through a real `uvicorn` subprocess, which failed identically
in three separate attempts (one inside the full suite, two isolated
reruns) with `HTTP Error 504: Gateway Timeout` at 158-172 seconds each
time — originating from `query.py`'s own `ModelTimeoutError` handling, not
a connectivity error.
Options for the deterministic bug: (a) leave it failing and note it as a
"regression" for the operator to sort out; (b) fix it by repointing it at
`"process_optimization"`, the one route still genuinely a stub.
Options for the live-latency failure: (a) keep retrying until it passes;
(b) weaken or skip the test; (c) fix the now-stale assertion shape (a
genuine, separate bug from the timing issue) and record the timing failure
itself as INCONCLUSIVE with evidence, per the autonomy charter's rule 6.
Chose: (b) for the deterministic bug; (c) for the live test — fixed
`test_query`'s assertion to branch on `body["route"]` the same way
`scripts/smoke_agents.py` already does, AND separately recorded three
consistent 504 timeouts as INCONCLUSIVE rather than retrying indefinitely
or silently marking the gate green.
Because: (a) for the deterministic bug would leave a known-wrong assertion
in the tree, which the charter explicitly prohibits papering over. For the
live test, (a) contradicts the charter's explicit three-attempt cap; (b)
(skipping/weakening) is explicitly prohibited ("Never delete or weaken a
test to make it pass"); (c) is exactly what the charter prescribes: fix the
part that is genuinely wrong (the stale assertion), and honestly report the
part that is an environment characteristic, not a code defect (the model
runtime is too slow in this sandbox to complete a cold classify+generate
round trip within a 180s client timeout, consistent with 4A/4B's own
recorded latency figures on comparable hardware).
Review priority: MEDIUM — no safety property depends on this test; it is
purely an end-to-end wiring smoke check duplicated, more thoroughly, by the
deterministic `tests/test_agents_maintenance.py`/`test_agents_knowledge.py`
suites. The operator should re-run `test_query` once against a warmed,
adequately-resourced model runtime to confirm it passes outright before
treating its live-path coverage as verified.
Reversible: n/a for the INCONCLUSIVE determination itself (a disclosure);
the two test fixes are ordinary test edits, reversible like any other.

## Phase 4R correction notice

The effective setting name is `KNOWLEDGE_RELEVANCE_FLOOR` under the
`WORKBENCH_` settings prefix; `WORKBENCH_KNOWLEDGE_RELEVANCE_FLOOR` is the
environment spelling. The default `0.0` is uncalibrated and is not a safety
claim. Phase 4R adds evidence sufficiency and identifier-support checks rather
than silently treating the score as a universal relevance boundary. The
authorization-language detector is supplemental, and approval metadata is
advisory until Phase 5. Free-text threshold extraction was retired unless
typed applicability is supplied; D-014 remains open.
