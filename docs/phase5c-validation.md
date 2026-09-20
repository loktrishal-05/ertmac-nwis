# Phase 5C validation — 2026-09-21

**PHASE 5C acceptance: COMPLETE.** Built on the accepted, committed Phase 5A
(`c76282d`) and Phase 5B (`c0addf0`). No commit or staging was performed by
this work. Phase 5D was not started.

## Repository baseline before work

- Branch `master`, HEAD `c0addf0` ("Phase 5B: add authenticated human
  approval workflow"), working tree clean except the pre-existing unrelated
  `frontend/src/App.jsx` modification and untracked `.codex/`/`claudex-loop/`
  — none of which this work touched.
- Reviewed `docs/phase5a.md`, `docs/phase5a-validation.md`, `docs/phase5b.md`,
  `docs/phase5b-validation.md`, the existing `AuditLog` model/route/schema
  (a Phase 2 placeholder, `GET /audit/log` always returned `[]`, zero rows
  ever written by any code in the repository), `ApprovalDecision`,
  `ActionRevision`, `GovernanceRequest`, `AgentRun`, `User`/authentication,
  `app.services.approval`, `app.services.governance`, `app/api/routes/query.py`,
  `app/api/routes/approvals.py`, `app/api/routes/auth.py`,
  `app.services.canonicalization`, `app/db/base.py`, and the full Alembic
  migration history before writing any code.

## Repository state after work (before any commit)

```
 M backend/app/api/routes/approvals.py
 M backend/app/api/routes/audit.py
 M backend/app/api/routes/auth.py
 M backend/app/db/models/__init__.py
 M backend/app/schemas/audit.py
 M backend/app/services/approval.py
 M backend/app/services/governance.py
 M backend/tests/test_foundation.py
 M backend/tests/test_phase5a.py
 M backend/tests/test_phase5b.py
 M frontend/src/App.jsx                          (pre-existing, untouched)
?? .codex/                                        (untouched)
?? backend/alembic/versions/0007_phase5c_audit_chain.py
?? backend/app/db/models/audit_event.py
?? backend/app/services/audit.py
?? backend/tests/test_phase5c.py
?? backend/tests/test_phase5c_postgres.py
?? claudex-loop/                                  (untouched)
?? docs/phase5c.md
?? docs/phase5c-validation.md
```

Only backend files listed above (plus this pair of docs) were changed by
this session's work; `frontend/src/App.jsx`, `.codex/`, and `claudex-loop/`
were never staged, modified, reverted, or cleaned.

## Audit architecture

See `docs/phase5c.md` in full. Summary: `app.db.models.AuditEvent`
(append-only, hash-chained, immutable), `app.db.models.AuditChainHead`
(mutable lock/cursor row, not part of the chain), `app.db.models.AuditCheckpoint`
(minimal local snapshot, not part of the chain, no external anchoring),
`app.services.audit` (the only writer — `append_event`, and the only
verifier — `verify_chain`, plus `create_checkpoint`), integrated into
`app.services.governance.govern_response`, `app.services.approval.apply_decision`/
`release_advisory`, `app/api/routes/auth.py`'s `login`, and
`app/api/routes/approvals.py`'s decision/release denial handlers. A new
read-only, role-gated `app/api/routes/audit.py` (`GET /audit/log`,
`GET /audit/verify`) replaces the old dead placeholder.

## Database changes / migration created

`0007_phase5c_audit_chain` (follows `0006_phase5b_approvals`): creates
`audit_chain_heads`, `audit_events` (with the `event_hash`/
`canonical_event_json` binding `CHECK`, the bounded `event_type`/`actor_kind`
vocabulary `CHECK`s, and `UNIQUE(chain_id, sequence_number)` +
`UNIQUE(event_hash)`), and `audit_checkpoints`, plus a
`reject_audit_event_mutation()` trigger function and `BEFORE UPDATE OR
DELETE` triggers on `audit_events`/`audit_checkpoints`. No Phase 5A/5B table
is touched. `alembic upgrade head`/`alembic check` both pass against the
live PostgreSQL database (`0007_phase5c_audit_chain (head)`, "No new upgrade
operations detected"); downgrade-to-`0006`-and-back is exercised by
`test_phase5c_postgres.py::test_migration_downgrade_upgrade_and_metadata`
and passed.

One real bug was found and fixed during this work, not hidden: the first
migration draft declared `audit_events.payload` as plain `sa.JSON()`, which
mismatched the model's `JSON().with_variant(JSONB(), "postgresql")` and
failed `alembic check` ("New upgrade operations detected" — a `modify_type`
to JSONB) the first time it was actually applied to live PostgreSQL. Fixed
to `postgresql.JSONB()` in the migration, matching the model and every other
JSON-bearing Phase 4 table's existing convention (`AgentRun.warnings`, etc.);
the partially-applied first attempt was cleanly rolled back (tables/function
dropped, `alembic_version` pointer restored to `0006`) before reapplying.

## Event schema

`AuditEvent`: `id` (= event_id), `schema_version` (fixed
`"phase5c-audit-v1"`), `chain_id` (fixed `"workbench-governance-v1"` in
production), `sequence_number`, `occurred_at`, `actor_id`/`actor_kind`
(`user`/`system`/`anonymous`), `event_type` (9-value bounded vocabulary —
see `docs/phase5c.md`), `request_id`/`action_revision_id`/`decision_id`
(nullable FKs, set where applicable), `payload` (JSON/JSONB, structured
investigation metadata, never a secret), `canonical_payload_hash`,
`previous_hash`, `canonical_event_json`, `event_hash`. Full column table in
`docs/phase5c.md`, "Event schema".

## Canonicalization / hash design

Reuses `app.services.canonicalization.canonical_json`/`canonical_hash`
(Phase 5A) byte-for-byte — no second canonicalization implementation.
`event_hash = sha256(canonical_json(envelope))`, where `envelope` binds
`schema_version`, `chain_id`, `sequence_number`, `event_id`, `occurred_at`,
`actor_id`, `actor_kind`, `event_type`, `request_id`, `action_revision_id`,
`decision_id`, `canonical_payload_hash`, and `previous_hash` — exactly the
required field set, no more, no less. `canonical_payload_hash` is a nested
hash of the payload dict, normalized to plain JSON-safe values
(`app.services.audit._json_safe`) before hashing so it survives a JSONB
round trip unchanged. No `repr()`; no dict-insertion-order dependence
(`canonical_json` always sorts keys); `allow_nan=False` rejects NaN/infinity
at two layers (the `_json_safe` normalization pass and `canonical_json`
itself). Fixed deterministic vector:
`test_phase5c.py::test_fixed_genesis_vector` pins the exact genesis hash for
the production chain id.

## Genesis design

`app.services.audit._genesis_previous_hash(chain_id)` — a pure function of
`chain_id` alone (`canonical_hash({"schema_version": ..., "genesis_marker":
"PHASE5C_AUDIT_CHAIN_GENESIS", "chain_id": chain_id})`), reproducible offline
without any database row. Event #1's `previous_hash` always equals this
value; there is no stored "genesis row."

## Append/locking design

`app.services.audit.append_event`: `SELECT ... FOR UPDATE` the chain's
`audit_chain_heads` row (get-or-create via `ON CONFLICT DO NOTHING`) →
allocate `sequence_number`/`previous_hash` from the locked row → compute
`canonical_payload_hash`/envelope/`canonical_event_json`/`event_hash` →
`session.add` the event and advance the head row → `session.flush()` (never
commits; the caller commits together with the state change it describes).
Matches the task's own diagram exactly. See `docs/phase5c.md`, "Append /
locking design", for the full reasoning on why the lock is correctness, not
optimization.

## Database immutability enforcement

`reject_audit_event_mutation()` trigger, `BEFORE UPDATE OR DELETE` on
`audit_events`/`audit_checkpoints` — real PostgreSQL, not ORM convention.
Proven: `test_phase5c_postgres.py::test_raw_sql_update_of_audit_event_denied`
and `test_raw_sql_delete_of_audit_event_denied` (raw SQL, bypassing the
application entirely, both rejected with `DBAPIError`). Additionally, a
`CHECK (event_hash = encode(sha256(convert_to(canonical_event_json,
'UTF8')), 'hex'))` constraint rejects a raw `INSERT` with a mismatched hash
(`test_event_hash_binding_check_rejects_mismatched_raw_insert`). Per-role
`GRANT`/`REVOKE` DB privilege separation was considered and not implemented
(documented as a future hardening option in `docs/phase5c.md` — consistent
with Phase 5A/5B never separating DB roles either).

## Governance/approval events integrated

`GOVERNED_REVISION_CREATED` (mandatory, same transaction as revision
creation), `LOGIN_SUCCESS` (mandatory, same transaction as the session),
`LOGIN_FAILURE`/`APPROVAL_AUTHORIZATION_DENIED`/`ADVISORY_RELEASE_DENIED`
(best-effort, never turn a correct 401/403 into a 500),
`APPROVAL_DECISION_APPROVE`/`REJECT`/`REVOKE` (mandatory, same transaction as
the decision, only on the actual confirmed winner — never on a losing race
or idempotent retry), `ADVISORY_RELEASE_SUCCESS` (mandatory, own
transaction). Full trigger-point table in `docs/phase5c.md`. Actor and
governed-object IDs verified correct in `test_phase5c.py`
(`test_pending_revision_creation_audited`, `test_approve_audited`,
`test_advisory_release_audited`, etc.) — e.g. `decision_id` on the
`APPROVAL_DECISION_APPROVE` row is asserted equal to the actual inserted
`ApprovalDecision.id`, not merely present.

## Verification service

`app.services.audit.verify_chain` — deterministic Python only, never an LLM.
Walks events for a chain in `sequence_number` order, independently
recomputes every hash from each row's own stored columns, and returns
`{valid, chain_id, events_checked, first_sequence, last_sequence, head_hash,
first_error_sequence, error_type}`, stopping at the first inconsistency.
`error_type` vocabulary: `sequence_gap`, `sequence_out_of_order`,
`duplicate_sequence_number`, `wrong_chain_id`, `previous_hash_mismatch`,
`payload_hash_mismatch`, `event_hash_mismatch`.

## API changes

`GET /audit/log?limit=100` (reviewer/admin, most recent events,
`sequence_number DESC`, `limit` capped at 500) and `GET /audit/verify`
(reviewer/admin, the `verify_chain()` result) — both read-only, role-gated
the same way as the Phase 5B approvals list. The dead Phase 2
`AuditLogResponse` schema (confirmed referenced nowhere else in the
codebase) was retired in favor of `AuditEventResponse`/`AuditVerifyResponse`.
`test_append_event_rejects_client_supplied_hash_fields` confirms
`append_event`'s own signature has no `event_hash`/`previous_hash` parameter
at all — passing either raises `TypeError`, not a silently-ignored value.

## Concurrency behavior

Real PostgreSQL, 8 concurrent threads appending to one fresh chain
simultaneously
(`test_phase5c_postgres.py::test_concurrent_appends_produce_unique_monotonic_sequence_and_one_chain`):
resulting sequence numbers are exactly `{1..8}` — no duplicates, no gaps, no
lost writes, no forked heads; `verify_chain` reports the resulting chain
fully `valid` with `events_checked == 8`; the `audit_chain_heads` cursor's
final state matches `verify_chain`'s independently-recomputed head. SQLite
is never used to support this claim (its `with_for_update()` compiles to no
real lock, matching Phase 5A/5B's own documented limitation) — only the real
PostgreSQL test does.

## Checkpoint/anchor status

Implemented: `app.db.models.AuditCheckpoint`,
`app.services.audit.create_checkpoint` — a minimal, local-only, append-only
snapshot of a chain's current head. Not implemented, and not claimed: any
external/off-host anchoring (no cloud dependency, no notarization service,
no blockchain). Documented as a future hardening option in `docs/phase5c.md`.
Exercised by `test_checkpoint_records_current_head` and
`test_checkpoint_empty_chain_returns_none`.

## Legacy audit handling

`app.db.models.AuditLog` (Phase 2): confirmed via full-repo grep before any
code was written that it has zero rows ever written by any code in this
repository, and is never touched by the Phase 5C migration. Not
retroactively claimed to be hash-chained history.
`verify_chain` structurally cannot see it (queries `AuditEvent` only) —
confirmed by `test_phase5c.py::test_legacy_audit_log_is_not_chained_history`
(SQLite, structural check) and, with a real inserted row against real
PostgreSQL JSONB (`AuditLog.event_data` cannot be created on SQLite),
`test_phase5c_postgres.py::test_legacy_audit_log_row_is_not_chained_history`.
The Phase 5C chain starts from its own documented genesis; nothing earlier
is retroactively covered.

## Tests added

- `backend/tests/test_phase5c.py` — 32 tests: `AuditChainTests` (27, direct
  service-level — hashing/chain algorithm tests 1-10 from the task's list,
  ORM-level immutability, governance/approval integration 17-22 plus a
  replay-does-not-double-audit check, checkpoint, security tests 23/26,
  legacy) and `AuditHTTPTests` (5, real HTTP layer via `TestClient` —
  unauthenticated/requester/reviewer role gating on both audit routes, and
  login failure audited without leaking the attempted password).
- `backend/tests/test_phase5c_postgres.py` — 6 opt-in
  (`WORKBENCH_TEST_POSTGRES=1`) tests against real PostgreSQL in an isolated
  schema: raw SQL `UPDATE`/`DELETE` rejected by the trigger, a raw `INSERT`
  with a mismatched `event_hash` rejected by the `CHECK` constraint, real
  8-thread concurrent-append correctness, a real inserted legacy `AuditLog`
  row confirmed invisible to `verify_chain`, and migration
  downgrade/upgrade/`check`.

Existing tests updated (necessary consequences of Phase 5C integration, not
weakenings): `test_phase5a.py` and `test_phase5b.py`'s SQLite `TABLES`
fixture lists gained `AuditChainHead`/`AuditEvent` (needed once
`govern_response`/`apply_decision` started writing audit rows inside those
same tests' transactions); `test_phase5b.py`'s two direct
`release_advisory(...)` call sites gained the new required `actor=` keyword;
`test_foundation.py`'s `test_audit_and_sovereignty` (`GET /audit/log`
unauthenticated now 401s instead of returning the old permanent `[]`) and
`test_metadata_and_offline_migration` (table/model count 18 → 21 for the
three new Phase 5C tables).

## Test totals

| Suite | Result |
|---|---|
| `compileall` (app, alembic, scripts, tests) | PASS |
| Phase 5A deterministic + PostgreSQL (`test_phase5a.py`, `test_phase5a_postgres.py`) | 33 passed, 8 subtests passed — unchanged |
| Phase 5B deterministic + PostgreSQL (`test_phase5b.py`, `test_phase5b_postgres.py`) | 43 passed — unchanged behavior (existing call sites updated for the new `actor=` keyword only) |
| Phase 5C deterministic (`test_phase5c.py`) | **32 passed** |
| Phase 5C PostgreSQL opt-in (`test_phase5c_postgres.py`) | **6 passed** |
| `test_agents*.py`, `test_phase4_repair.py` (Phase 4/4R regressions) | included below, all passed |
| Phase 3 regressions (`test_knowledge.py`, `test_pid.py`, `test_hybrid.py`, `test_structured.py`) | included below, all passed |
| `test_evaluation_asset_guard.py` (benchmark hash guard) | included below, passed; benchmark assets unchanged |
| Full backend suite, `WORKBENCH_TEST_POSTGRES=1` | **393 discovered, 392 passed, 0 failed/errored, 1 skipped** (live-model opt-in only, not re-run this session — unrelated to Phase 5C and already validated live in Phase 5B/5A) |
| Alembic upgrade/check (live PostgreSQL) | PASS, head `0007_phase5c_audit_chain` |
| Docker Compose config | PASS |
| Frontend build | PASS |
| Frontend lint | PASS |
| `git diff --check` | PASS (only pre-existing CRLF/LF autocrlf warnings, no actual whitespace errors) |

## Live PostgreSQL results

- `sovereign_workbench` database, live Docker container, at
  `0007_phase5c_audit_chain` head before and after this session's test runs
  (confirmed via `alembic current`/`alembic check`).
- `test_phase5c_postgres.py`'s real 8-thread concurrent-append test: exactly
  the sequence set `{1..8}`, zero duplicates/gaps, `verify_chain` fully
  valid, head-pointer/verifier agreement — see "Concurrency behavior" above.
- Raw SQL `UPDATE`/`DELETE` against `audit_events` both raised (PostgreSQL
  trigger), matching the same immutability guarantee Phase 5A/5B already
  established for their own tables, now extended to the audit chain.
- A raw SQL `INSERT` with a deliberately mismatched `event_hash` was
  rejected by the `event_hash_binding` `CHECK` constraint directly at the
  database level, not only by application code.
- A real `AuditLog` (Phase 2) row, inserted with genuine PostgreSQL JSONB
  `event_data`, confirmed invisible to `verify_chain`.

## Tampering tests (all detected as required)

Payload modification, metadata (event_type) modification, `event_hash`
modification, `previous_hash` modification, deleted middle event, inserted
event (forged `previous_hash`), reordered event (content legitimately hashed
"as if" a different sequence number, stored at another), sequence gap,
duplicate sequence number (rejected at insert by the unique constraint,
never silently accepted), and a chain-id splice (a row whose stored
`chain_id` column matches the chain being verified but whose `event_hash`
was actually computed embedding a *different* `chain_id`) — every one of the
task's 10 hashing/chain scenarios is a passing, independently-verified test
in `test_phase5c.py`, each asserting both `valid == False` and the specific
`error_type`/`first_error_sequence` reported.

## Security/bypass tests (all denied or absent as required)

`append_event(..., event_hash="...")`/`append_event(..., previous_hash="...")`
→ `TypeError` (no such parameter exists at all, not merely ignored).
Unauthenticated/`requester`-role callers of `GET /audit/log`/`GET
/audit/verify` → `401`/`403`. A login failure's audit payload never contains
the attempted password (`test_login_failure_is_audited_without_password`,
and structurally at the service level,
`test_no_secrets_in_audit_payload` scans every payload written during a full
governed-revision flow for `"password"`/`"token"`/`"session"` substrings).
Direct ORM mutation attempts on an `AuditEvent` row raise the immutability
`ValueError` even for an authenticated reviewer with direct database-session
access (`test_unauthorized_role_cannot_mutate_audit_via_orm`) — no route
exists that would let a client reach this path via the API at all.

## Files changed

See "Repository state after work" above for the exact list. New: 5 files
(`app/db/models/audit_event.py`, `app/services/audit.py`,
`alembic/versions/0007_phase5c_audit_chain.py`, `tests/test_phase5c.py`,
`tests/test_phase5c_postgres.py`) plus this doc pair. Modified: 10 backend
files. `frontend/src/App.jsx`, `.codex/`, `claudex-loop/` — not touched.

## Unresolved issues

- No BLOCKER/HIGH issues.
- External/off-host checkpoint anchoring is not implemented (documented,
  intentional scope boundary — see "Checkpoint/anchor status").
- Per-role PostgreSQL `GRANT`/`REVOKE` privilege separation for the audit
  tables is not implemented (documented, matches existing Phase 5A/5B
  precedent of a single application DB role).
- Best-effort (non-fail-closed) audit events — `LOGIN_FAILURE`,
  `APPROVAL_AUTHORIZATION_DENIED`, `ADVISORY_RELEASE_DENIED` — can, by
  design, occasionally go unrecorded if the immediate follow-up append fails
  (e.g. a transient DB error right after the deny), without affecting the
  correctness of the 401/403 response itself. This is a deliberate,
  documented trade-off (see `docs/phase5c.md`, "Atomic governance/audit
  behavior"), not an oversight.
- No frontend audit-log UI (explicitly out of scope for this phase).

## Exact git status

See "Repository state after work" above (identical content, git-status form).

## Final verdict: **PHASE 5C COMPLETE**
