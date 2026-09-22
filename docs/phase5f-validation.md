# Phase 5F independent security acceptance — REPAIR COMPLETE

Audit started: 2026-09-21. Audit completed: 2026-09-22 (NEEDS REPAIR, no
implementation changes). Repair pass: 2026-09-22 (this update). Everything
below the "## Repair pass" heading documents the repair; everything above it
is the original, unmodified audit report, preserved as the historical record
of what was found and how it was reproduced.

Final verdict: **PHASE 5F REPAIR COMPLETE.** All three HIGH and all three
MEDIUM findings are fixed with smallest fail-closed changes, using the
original adversarial tests as reproductions. No architecture redesign, no
broad refactor of working 5A-5E functionality. Not committed. Phase 6 not
started.

## Resume instructions

Read git status/diff, this report, and `docs/phase5f-results/` before continuing.
Do not commit, start Phase 6, or change implementation during this audit.
Adversarial probes are preserved in `backend/tests/test_phase5f_security.py`.
Only test schemas prefixed `test_phase5f_` may be modified by destructive probes.

## Baseline

HEAD: `0be5a50` (Phase 5D hardening). Contrary to the task premise, Phase 5E
is present but **uncommitted**. Review targets the current working tree.
Pre-existing changes: backend/app/agents/safety_language.py,
backend/app/api/routes/query.py, backend/app/db/models/audit_event.py,
backend/tests/test_agents.py, frontend/src/App.jsx. Pre-existing untracked:
.codex/, claudex-loop/, migration 0009, preflight.py, test_phase5e.py,
docs/phase5e.md, docs/phase5e-validation.md. Preserve all of these.

## Progress

Complete. The checkpoints below preserve the actual execution history;
their pending statements are superseded by the final results at the end.

## Checkpoint 1

- Existing full backend suite with PostgreSQL enabled: 472 discovered,
  471 passed, 1 live-model test skipped; exit 0. Includes Phases 5A–5E,
  PostgreSQL concurrency/immutability, gateway sovereignty, benchmark guard.
  Log: phase5f-results/backend-full.txt.
- Frontend lint passed. Build initially hit sandbox `spawn EPERM`; authorized
  retry passed. Both original failure and retry logs retained.
- Compileall, Alembic check, Compose config passed. PostgreSQL container healthy;
  Qdrant collections and Ollama qwen3.5:9b available. No HTTP server at port 8000.
- Additional PostgreSQL suite first run: 16 tests, 7 assertion failures,
  1 probe error (duplicate audit hash correctly rejected on insertion).
  Correct that probe to treat database rejection as prevention, then rerun it.
- Reproduced candidates: manipulated/stale ORM role accepted; release succeeds
  after interleaved committed revocation; TRUNCATE audit_events reports a valid
  empty chain; stored request replay skips preflight; SOP suffix hides imperative;
  equipment keyword permits unrelated movie query. Severity analysis pending.
- No implementation repairs made. Live HTTP/model flow still pending.

## Checkpoint 2 — reproduced findings (no repairs)

Final first 16 added probes: 9 passed, 7 failed, zero errors after fixing
the audit-insert probe to recognize database rejection. The original probe
error log is retained. Four additional targeted probes are running separately.

### HIGH H1 — mutable/stale ORM principal bypasses service authorization

`backend/app/services/approval.py:apply_decision` uses `session.get(User, id)`
as a purported fresh authoritative read. SQLAlchemy returns the identity-map
object when already loaded. Reproduce with
`test_manipulated_attached_user_role_denied`: load an ordinary requester,
set its role to `admin`, call apply_decision under `session.no_autoflush`;
the service accepts approval. The test rolls back. A second probe loads a
reviewer, downgrades its database role in another committed connection, and
the old session still approves (`test_stale_reviewer_role_denied`).
Impact: direct service authorization can trust forged/stale authority.
Smallest repair: reject dirty principal authority fields, read authoritative
identity/role without autoflushing caller changes or reusing cached entities,
and define locking for concurrent role revocation. Add both regressions.

### HIGH H2 — committed revocation can precede successful release

`governance.assert_release_allowed` / `approval.release_advisory` do not lock
the revision across state validation and release commit. Reproduce with
`test_revocation_between_validation_and_release_denied`: a deterministic
hook in evidence verification commits REVOKE in a separate real PostgreSQL
session after the approval-state check; release still succeeds and writes
ADVISORY_RELEASE_SUCCESS. No mocked database or mocked approval result.
Impact: a revoked decision can still produce an authoritative release.
Smallest repair: serialize release against decision/revoke on the same
revision lock, holding it through release audit commit; also test evidence
mutation concurrent with verification and define that transaction boundary.

### HIGH H3 — audit truncation is neither prevented nor detected

`audit.verify_chain` verifies only rows that remain; it never compares the
end to stored head/checkpoints. Row-level immutability triggers do not cover
TRUNCATE. `test_audit_truncate_not_reported_valid` creates a three-event
chain, TRUNCATEs audit_events using the configured DB role without disabling
triggers, then observes valid=True with zero events. Transaction rolled back.
Requires database execution privileges, not demonstrated as a public HTTP
exploit. Still violates the requested persistence/tamper-detection boundary.
Smallest repair: prevent TRUNCATE on audit tables and compare verification
with independently retained expected head/checkpoints, so missing tails do
not appear valid. Full database-admin compromise remains outside this guarantee.

### MEDIUM M1 — replay skips current preflight

`api/routes/query.py:query` returns `replay_request` before `run_preflight`.
Create a stored governed draft for `Start P-204` via the supported service
(also models a pre-5E draft), then POST its original request_id/query: a draft
returns instead of the deterministic refusal. No model call or new execution
authority was observed. Put preflight before replay, or explicitly validate
replay against current guardrails.

### MEDIUM M2 — informational word suppresses unsafe imperative detection

`preflight._detect_unsafe_action`: `Start P-204 using the SOP` returns ALLOW
because the presence of `SOP` skips the sentence. Detect imperative intent
before applying the informational exception. The closed read-only tool set
still prevents physical execution.

### MEDIUM M3 — domain restriction defeated by equipment keyword

`preflight.classify_domain`: `At Northbridge Refining Co pump division,
recommend a movie for tonight.` returns ALLOW. Any equipment noun takes
priority over an explicit unrelated intent. Classify the requested task;
conflicting context should clarify/refuse rather than permit automatically.

## Live progress

The real HTTP probe runs its own loopback Uvicorn process with an isolated
test_phase5f_ schema, copies existing source records (no public writes), uses
existing Qdrant read-only, and calls only local Ollama. Hugging Face/network
model downloads are disabled. Live events append immediately to
phase5f-results/live-http.jsonl; server log is live-server.txt.
Authenticated logins, out-of-scope refusal, injection refusal, and clarification
have completed. Real model company/governed queries and release flow pending.

## Resume reconciliation and final results

On 2026-09-22, git status/diff still matched the recorded implementation
baseline. Phase 5E remains uncommitted; HEAD remains 0be5a50. The live
process had finished with exit 0 and cleaned up its schema. Completed runs
were reused, not repeated. Only result summarization, compilation of the
new audit artifacts, cleanup verification, and this final report remained.

### Security invariants

PASS means the inspected paths and executed probes satisfied the invariant;
it is not a proof against every possible natural-language adversarial input.

| # | Invariant | Result / evidence |
|---|---|---|
| 1 | Model output cannot authorize | PASS — Phase 5A/5B tests and quoted-injection/model-authority PostgreSQL probe |
| 2 | Client authority fields grant nothing | PASS — extra fields rejected; forged headers/cookies rejected |
| 3 | Ordinary requester cannot approve by any path | FAIL — H1 attached/stale principal bypass; ordinary HTTP and detached forged-role calls denied |
| 4 | Self-approval fails | PASS — PostgreSQL probe and real HTTP 403 |
| 5 | Revision A approval cannot release B | PASS — PostgreSQL substitution probe; real wrong-revision 403 |
| 6 | Request/proposal hash mismatch fails closed | PASS — both hashes probed in PostgreSQL |
| 7 | Rejected/revoked/expired cannot release | FAIL — sequential cases pass, concurrent revocation H2 fails |
| 8 | Duplicate/replayed decisions preserve state | PASS — existing idempotency/concurrency tests; revoked approval replay cannot release |
| 9 | Manifest substitution fails | PASS — DB mutation prevented, separate revision not released; deterministic hash mismatch tests |
| 10 | Missing document provenance fails | PASS — hardening regressions and new PostgreSQL probe |
| 11 | Missing/unresolved sensor evidence fails | PASS — hardening regressions and new PostgreSQL probe |
| 12 | OCR integrity grants no topology/isolation authority | PASS — dedicated tests; live output retains OCR warning |
| 13 | Audit history cannot be silently removed/changed | FAIL for TRUNCATE (H3); raw UPDATE/DELETE are prevented |
| 14 | Middle corruption/deletion/reorder/insertion detected/prevented | PASS — PostgreSQL probes (trigger disabled transactionally only to test verifier); duplicate insertion prevented |
| 15 | Concurrent audit appends cannot fork | PASS — existing eight-worker PostgreSQL test |
| 16 | Out-of-domain requests cannot reach model | FAIL for keyword camouflage M3; plain movie request refused without model |
| 17 | Deterministic REFUSE/CLARIFY invokes no model | PASS — HTTP tests mock/assert zero graph calls; real HTTP refusal/clarification also succeeds |
| 18 | Injection cannot grant approval/role/scope/safety authority | PASS in executed authority probes; pattern matching is bounded, not a universal injection detector |
| 19 | Plant requests create no control capability | PASS — seven read-only tools; M2 is a routing weakness, not a demonstrated write capability |
| 20 | Procedure information remains retrievable | PASS — SOP unit test and real company query (S3) |
| 21 | API/services share fail-closed enforcement | FAIL — H1, H2, and replay before preflight M1 |
| 22 | Legacy records not falsely trusted | PASS — existing legacy approval/evidence/audit tests; legacy drafts have the M1 replay limitation |
| 23 | No hosted AI introduced | PASS — gateway policy tests, inspected local runtime, real queries use local Ollama; model downloads disabled for live probe |
| 24 | Benchmark assets unchanged | PASS — two benchmark asset guards plus Phase 5E benchmark regression |

### Tests and checks

| Run | Result |
|---|---|
| Original full backend suite, PostgreSQL enabled | 472 discovered: 471 passed, 1 optional live-model test skipped |
| Included Phase 5A deterministic / PostgreSQL | 30 / 3 passed |
| Included Phase 5B deterministic / PostgreSQL | 37 / 6 passed |
| Included Phase 5C deterministic / PostgreSQL | 32 / 6 passed |
| Included Phase 5D deterministic / PostgreSQL | 37 / 7 passed |
| Included Phase 5E | 35 passed |
| New Phase 5F probes, first final batch | 16: 9 passed, 7 failed, 0 errors |
| New Phase 5F probes, additional batch | 4 passed |
| Combined distinct tests, across these runs | 492: 484 passed, 7 failed, 1 skipped |
| Alembic check, compileall, Compose config, git diff --check | PASS |
| Frontend build / lint | PASS / PASS; build passed after sandbox EPERM retry |
| New audit script/test compilation on resume | PASS |

No broad test rerun on resume. The one skipped historical live-model unittest
is not reported as passed: separate real-model HTTP acceptance flows below
completed. The initial audit insertion-probe error was a correctly blocked
duplicate hash, not a product bug; corrected probe accepts prevention and
passes. Both initial and final logs are retained.

Required adversarial categories were executed: forged roles (detached,
attached, stale), requester direct service approval, self-approval, revision
and both hash substitutions, replay, approve/reject race, manifest substitution,
missing document version, unresolved sensor readings, audit corruption/middle
deletion/reordering/insertion/concurrent append/truncation, injection and quoted
injection, company-keyword domain camouflage, unsafe imperative and SOP
information, scope escalation, model approval/scope claims, unauthenticated
and unapproved release, expired sessions, and mandatory audit-write failure.

### Live stack and end-to-end HTTP results

PostgreSQL: healthy; real migrations, constraints, source drift, concurrent
decisions/appends, and destructive isolated-schema probes completed.
Qdrant: HTTP 200; existing hybrid collection was used by the two real queries.
Ollama: qwen3.5:9b available locally; two real model-backed queries completed.
The indexed corpus is synthetic validation data, not real plant operating
guidance. Successful software validation does not validate operational advice.

| Flow | Real HTTP result |
|---|---|
| A: company/SOP query | 200, S3 INFORMATIONAL, 138.19 s |
| B: out of scope | 200, deterministic S5 refused |
| C: prompt injection | 200, deterministic S5 refused |
| Additional: uncertain input | 200, clarification_required |
| D: governed maintenance recommendation | 200, S4 PENDING_REVIEW, 151.38 s |
| F: reviewer-author attempts self-approval | 403 |
| G: mismatched expected revision / unknown revision release | 409 / 403; both hash substitutions separately denied by real PostgreSQL service probes |
| E: independent reviewer approval | 200 APPROVED |
| I: exact approved advisory release | 200 RELEASED, evidence VERIFIED |
| H: copied document source drift after approval | 403, document_source_hash_mismatch |
| Audit after flow | Valid 13-event chain |

`phase5f-results/live-http.jsonl` contains incremental response evidence;
`live-summary.json` provides a compact index. The live Uvicorn process stopped
and its test schema was dropped. No public source/Qdrant records were changed.
The happy path passes; overall governance acceptance fails H1–H3.

### Findings and disposition

BLOCKER: none identified. HIGH: H1, H2, H3 above, with exact test-method
reproductions and smallest recommended repairs. MEDIUM: M1, M2, M3 above.
LOW: none newly identified. INFORMATIONAL: Phase 5E is uncommitted despite
the task premise; assessment applies to the inspected working tree.
Full-database-admin compromise/off-host anchoring is not claimed solved;
H3 reproduces an undetected ordinary TRUNCATE with the configured DB role.

To reproduce only the added probes from backend (PowerShell):

```powershell
$env:WORKBENCH_TEST_POSTGRES='1'
$env:PYTHONPATH='tests'
.\.venv\Scripts\python.exe -m unittest test_phase5f_security -v
```

The seven failing assertions remain visible for repair validation. Do not
mark them expected failures. Only audit artifacts were added by this review.
Exact final git status is preserved in `phase5f-results/final-git-status.txt`.

**PHASE 5F NEEDS REPAIR. Can Phase 6 begin? NO.** (original audit verdict,
superseded below.)

## Repair pass (2026-09-22)

Smallest fail-closed changes only. No architecture redesign, no broad
refactor of working Phase 5A-5E functionality. The seven originally-failing
adversarial assertions (`test_phase5f_security.py`) were not deleted,
skipped, or turned into expected failures -- they were made to pass by
fixing the underlying product code, and two of them were additionally
strengthened (see H3 below) because the fix made the original reproduction
stronger than merely "detect after the fact."

### HIGH H1 — cached principal authorization bypass — FIXED

**Repair:** `app.services.approval.apply_decision`
(`backend/app/services/approval.py`). The authorization check no longer
uses `session.get(User, id)` -- which, per SQLAlchemy's identity map, can
return an already-attached, possibly-mutated or stale cached `User` object
instead of issuing a real query. It now does a plain **column-only** SELECT
(`select(User.role).where(User.id == reviewer_id)`), which is never served
from the identity map and always executes a fresh query against the current
database row, wrapped in `session.no_autoflush` so a caller's dirty,
mutated `User.role` attribute can never be flushed to the database as a
side effect of merely checking authorization. Every later use of
`reviewer.id` in the function was changed to the already-extracted
`reviewer_id` local variable, so nothing downstream ever re-touches the
untrusted object either. No locking was added for role changes themselves
(no code path in this repository lets a role change race a decision on the
same revision the way an approval/revoke race can -- see H2); a fresh,
autoflush-safe read was judged the smallest correct fix, documented in the
function's own docstring as the explicit alternative to locking.

**Regression tests** (`test_phase5f_security.py`, real PostgreSQL):
`test_manipulated_attached_user_role_denied` (in-memory role mutated to
admin, autoflush suppressed by the test itself -- denied, and the database
row is confirmed never corrupted by the check), `test_stale_reviewer_role_denied`
(role demoted in the database by a separate committed connection after the
object was loaded -- denied), `test_requester_and_detached_forged_role_denied`
(both a real loaded object and a fully detached forged `SimpleNamespace` --
denied), `test_self_approval_denied` (unaffected regression).

**Result:** all pass against real PostgreSQL (`WORKBENCH_TEST_POSTGRES=1`).

### HIGH H2 — revocation/release race — FIXED

**Repair:** new `app.services.governance.assert_still_approved_under_lock`
(`backend/app/services/governance.py`), called from
`app.services.approval.release_advisory` immediately after the existing
`assert_release_allowed` validation and before building/auditing/committing
the release. It takes the identical `SELECT ... FOR UPDATE` row lock
`apply_decision._load_binding_and_revision` already takes for every
approve/reject/revoke decision on a revision, then re-reads the current
ledger state under that lock. This is deliberately a SEPARATE, LATER lock
point rather than locking inside `assert_release_allowed` itself: that
function's own evidence-integrity check (`verify_manifest`) does real,
unlocked work, and locking across it would either accomplish nothing (the
race would just move earlier) or -- in the exact adversarial reproduction,
which injects the concurrent revoke synchronously inside `verify_manifest`'s
call stack via a mock -- deadlock the test against itself. Taking the lock
as the LAST gate before commit means a concurrent decision on this exact
revision can now only ever land strictly before this check (correctly
observed and denied) or strictly after this transaction's commit (blocked
until then by the identical row lock) -- never silently in between.

**Regression tests** (real PostgreSQL, no mocked database or approval
result): `test_revocation_between_validation_and_release_denied` (the
given reproduction -- a revoke committed via a separate real session,
injected synchronously inside `verify_manifest`, between validation and
commit -- now correctly denies release) and the new
`test_release_and_concurrent_revoke_serialize_deterministically`, which
proves the OTHER interleaving with two independent real threads and no
mocked concurrency: a revoke attempt started while release already holds
the final lock blocks (verified via a controlled sleep inside
`revision_detail`, called only after the lock is taken) until release
commits, and only then applies -- release succeeds AND the revoke
subsequently also succeeds (revoking an already-released advisory remains
allowed, since `RELEASED` is a response label only, never a persisted
ledger state, per `docs/phase5b.md`).

**Result:** both interleavings pass against real PostgreSQL.

### HIGH H3 — audit truncation undetected — FIXED (two independent layers)

**Repair 1 (prevention):** migration `0010_phase5f_repairs.py` adds a
`BEFORE TRUNCATE ... FOR EACH STATEMENT` trigger on `audit_events` and
`audit_checkpoints`, reusing the existing `reject_audit_event_mutation()`
function (created in `0007`, never dropped) -- the same immutability
strategy already used for `UPDATE`/`DELETE`, now extended to the one
statement-level operation row triggers cannot intercept. This is
consistent with, not a redesign of, the existing strategy; per-role
`GRANT`/`REVOKE` separation remains out of scope (documented in
`docs/phase5c.md` as an already-declined future hardening option, and this
repository's single configured database role is unchanged by this
repair). **This does not defend against a role privileged enough to
disable the trigger first** (e.g. `ALTER TABLE ... DISABLE TRIGGER USER`)
-- the same "tamper-evident, not tamper-proof" limitation Phase 5C's row
triggers already carry, never claimed otherwise.

**Repair 2 (detection, defense in depth):** `app.services.audit.verify_chain`
(`backend/app/services/audit.py`) now checks, whenever an empty event set
is found for a `chain_id`, whether the separate, mutable
`audit_chain_heads` cursor row for that same chain claims
`next_sequence_number > 1` -- proof events previously existed. If so, it
reports `valid: False, error_type: "chain_truncated"` instead of a false
`valid: True`. A chain that genuinely never had any events (no
`audit_chain_heads` row at all) is unaffected and still verifies as valid
(`test_empty_chain_verifies` in `test_phase5c.py`, unchanged).

**Test changes:** the original reproduction, `test_audit_truncate_not_reported_valid`,
assumed TRUNCATE would succeed against the live connection; Repair 1 makes
that assumption false for this repository's configured role, so it was
renamed to `test_audit_truncate_is_rejected_by_the_database` and now
asserts the TRUNCATE itself raises `DBAPIError` (the identical pattern
`test_phase5c_postgres.py` already uses for `UPDATE`/`DELETE` rejection) --
a strictly STRONGER outcome than the original "succeeds, then detected"
premise, not a weakened one; the chain is confirmed to still verify as
valid afterward (nothing was actually lost). A new test,
`test_audit_truncate_not_reported_valid_if_trigger_bypassed`, reproduces
the ORIGINAL scenario exactly (disables the trigger first, mirroring the
existing corruption test's own established technique, then truncates) and
asserts Repair 2 still catches it via `chain_truncated` -- so the original
adversarial premise (TRUNCATE succeeding) remains covered, just now
requires the documented privileged bypass to reach it. One pre-existing,
non-adversarial Phase 5D test (`test_phase5d_postgres.py::
test_migration_downgrade_upgrade_and_metadata`) used TRUNCATE purely as
test housekeeping (clearing rows that would violate a downgraded
constraint) and needed the same disable/re-enable wrapping to keep working
-- this is unrelated to the Phase 5F adversarial suite and was not an
attack being probed.

**Result:** all three tests (prevention, bypassed-trigger detection, and
the unrelated migration housekeeping fix) pass against real PostgreSQL.

### MEDIUM M1 — replay skips current preflight — FIXED

**Repair:** `app/api/routes/query.py`'s `query()` handler. `replay_request`
still runs first, but ONLY to detect a genuine request_id/content conflict
(unchanged 409 behavior) -- its cached draft, if any, is held rather than
returned immediately. `run_preflight` then runs on every request,
cached-draft-pending or not. Only once preflight returns `ALLOW` is the
cached draft (if one exists) returned; a `REFUSE`/`CLARIFY` decision wins
even for a request_id with an existing stored governed draft, so a
guardrail tightened after a draft was created (or a draft created before
Phase 5E existed at all) can no longer be replayed around.

**Regression test:** the given `test_replay_cannot_skip_current_preflight`
(creates a governed revision directly via `create_revision` for
`query='Start P-204'`, bypassing `/query` entirely -- modeling exactly a
pre-5E/pre-repair stored draft -- then POSTs that same request_id/content;
now returns the deterministic refusal, never the stale draft, with zero
`run_graph` calls). Existing idempotency regression
(`test_phase5a.py::test_query_integration_replay_and_conflict`) is
unaffected: preflight runs on the same, still-in-scope content on both the
first and replayed calls, and the conflict-detection 409 path is reached
before preflight is ever evaluated.

**Result:** passes (SQLite deterministic suite and real PostgreSQL).

### MEDIUM M2 — unsafe action language — FIXED

**Repair:** `app.services.preflight._detect_unsafe_action`
(`backend/app/services/preflight.py`). The old `_INFORMATIONAL_MARKER`
exempted a sentence from the imperative-action check if it contained
"SOP"/"procedure"/etc. ANYWHERE, so a trailing justification clause could
hide a leading command ("Start P-204 **using the SOP**"). It is replaced
by `_QUESTION_OPENER`, anchored to `^` (the very start of the sentence
only) and restricted to genuine WH-style/fact-question openers
(what/which/when/why/how/does/do/did/who approved/describe/explain/
summarize/tell me about) -- deliberately EXCLUDING "can/could/would/will",
since "Can you start P-204?" is a polite imperative, not an informational
question, and must still be refused. A sentence is now exempted only if it
is ITSELF grammatically framed as a question from the start; an imperative
sentence that merely references a procedure elsewhere is not.

**Regression tests:** `test_informational_suffix_cannot_hide_operational_imperative`
(given reproduction: "Start P-204 using the SOP" -> REFUSE) plus the
brief's other named variants verified directly against `run_preflight`
("restart P-204 according to the procedure", "close XV-204D following the
SOP", "bypass the alarm according to the manual" -- all REFUSE); the
informational counter-examples remain allowed ("What does the SOP say
about starting P-204?", "What SOP describes shutdown of P-204?"). This is
sentence-structure composition (a start-anchored question-opener check
plus the existing bounded action-verb list), not naive single-keyword
blocking -- "SOP"/"procedure" mentioned anywhere no longer matters by
itself in either direction.

**Result:** passes (SQLite deterministic suite and real PostgreSQL).

### MEDIUM M3 — domain keyword stuffing — FIXED

**Repair:** `app.services.preflight.classify_domain`
(`backend/app/services/preflight.py`). The out-of-domain marker check
(movie/joke/sports/crypto/etc.) now runs FIRST and unconditionally, before
any tag/SOP/equipment-noun/phrase "strong signal" check -- previously a
strong signal short-circuited past the out-of-domain check entirely, so
stuffing in any equipment noun (or even a real equipment tag) let an
otherwise clearly unrelated request through. None of this workbench's
genuine industrial vocabulary collides with the bounded out-of-domain
marker list, so reordering the check never misclassifies a real industrial
query -- verified by the full existing IN_SCOPE example set still passing
unchanged (`test_phase5e.py::DomainClassificationTests`, all 12 still
green). This is strengthened deterministic composition (reordering which
signal is evaluated first), not a second classifier and not any LLM
involvement.

**Regression tests:** the given `test_company_equipment_keyword_cannot_allow_unrelated_query`
("At Northbridge Refining Co pump division, recommend a movie for
tonight." -> no longer `ALLOW`) plus the brief's two additional named
examples verified directly against `run_preflight` ("Write a movie review
about P-204." and "Tell me a joke about valve XV-204D." -- both now
`OUT_OF_SCOPE`/REFUSE even though each contains a real, specific equipment
tag). Legitimate industrial intent with no conflicting marker is confirmed
unaffected ("Review pump recommendation", "Show maintenance history for
P-204." -- both still `IN_SCOPE`/ALLOW).

**Result:** passes (SQLite deterministic suite and real PostgreSQL).

### Validation

| Check | Result |
|---|---|
| Targeted `test_phase5f_security.py` (real PostgreSQL) | 22 passed (21 original + 1 new HIGH-2 interleaving-B test), 0 failed |
| Phase 5A-5E combined, deterministic + PostgreSQL | 215 passed |
| Full backend suite, deterministic only | 449 passed, 22 skipped (PostgreSQL-gated), 23 deselected |
| Full backend suite, PostgreSQL enabled (`WORKBENCH_TEST_POSTGRES=1`) | **493 passed, 1 pre-existing unrelated skip, 0 failed** |
| `python -m compileall app alembic` | clean |
| `alembic upgrade head` / `alembic current` / `alembic check` | `0010_phase5f_repairs` (head); no drift |
| Benchmark hash guard (`test_evaluation_asset_guard.py`) | passes unchanged, included in the full-suite run above |
| `docker compose -f infra/docker-compose.yml config` | exit 0 |
| `npm run build` (frontend) | succeeds, 31 modules transformed |
| `npm run lint` (frontend) | zero violations |
| `git diff --check` | clean (only pre-existing LF/CRLF warnings) |

Qdrant and Ollama were not exercised in this repair pass: all six findings
are deterministic service-level logic, PostgreSQL row-locking/trigger
behavior, or regex composition -- none touch retrieval, embeddings, or
model inference, so a live model/vector-store round trip would exercise
nothing this repair changed. The audit's own live A-I HTTP flow (above)
already exercised the full real stack before this pass and is not
re-claimed as re-verified here.

### Remaining issues after repair

**BLOCKER:** none. **HIGH:** none remaining -- H1, H2, H3 all fixed and
regression-tested against real PostgreSQL. **MEDIUM:** none remaining --
M1, M2, M3 all fixed. **LOW:** none newly identified.

**Documented, disclosed limitations (not defects):**

- H3's DB-level TRUNCATE prevention does not defend against a role
  privileged enough to disable the trigger first (documented above); the
  verify_chain-side detection is the independent second layer for exactly
  that case. Full database-superuser compromise remains outside this
  system's threat model, exactly as Phase 5C already stated.
- The domain/injection/unsafe-action word lists remain bounded,
  hand-written, and admittedly incomplete -- unchanged from Phase 5E's own
  documented limitation, matching D-010's own "necessarily incomplete"
  precedent (`docs/phase4-decisions.md` D-010).
- `"What prerequisites are listed before restart?"` (one of MEDIUM-2's
  named informational examples) is not blocked as unsafe -- M2's actual
  concern -- but resolves to `CLARIFY` rather than `ALLOW`, because it
  names no equipment tag, SOP reference, or equipment noun at all (unlike
  the SOP-naming sibling example). This is judged correct, conservative
  behavior consistent with the existing "Tell me about pressure" ->
  `UNCERTAIN` precedent, not a regression: the request is genuinely
  equipment-ambiguous, and asking for clarification is the intended
  response to that, distinct from refusing it.

**PHASE 5F REPAIR COMPLETE.**
