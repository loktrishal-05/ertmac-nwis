# Phase 5B validation — 2026-09-20

**PHASE 5B acceptance: COMPLETE.** Built on the accepted, committed Phase 5A
(`c76282d`). No commit or staging was performed by this work. Phase 5C was
not started.

## Repository baseline before work

- Branch `master`, HEAD `c76282d` ("Phase 5A: add governance enforcement
  boundary"), working tree clean except the pre-existing unrelated
  `frontend/src/App.jsx` modification and untracked `.codex/`/`claudex-loop/`
  — none of which this work touched.
- Reviewed `docs/phase5a.md`, `docs/phase5a-validation.md`,
  `docs/phase4-repair.md`, the existing `User`/`Approval`/`AgentAction`
  models, `app/services/governance.py`, `app/schemas/query.py`, FastAPI
  dependency/router structure, `app/core/config.py`, and the Alembic
  history before writing any code.

## New dependency

`argon2-cffi>=23,<24` (added to `backend/requirements.txt`, installed) — the
password-hashing library, Argon2id by default (matches the task's stated
preference).

## Repository state after work (before any commit)

```
 M README.md
 M backend/app/api/router.py
 M backend/app/api/routes/approvals.py
 M backend/app/api/routes/query.py
 M backend/app/core/config.py
 M backend/app/db/models/__init__.py
 M backend/app/db/models/action_revision.py
 M backend/app/db/models/user.py
 M backend/app/main.py
 M backend/app/schemas/approval.py
 M backend/app/schemas/query.py
 M backend/app/services/governance.py
 M backend/requirements.txt
 M backend/tests/test_foundation.py
 M backend/tests/test_phase5a.py
 M frontend/src/App.jsx                          (pre-existing, untouched)
?? .codex/                                        (untouched)
?? backend/alembic/versions/0006_phase5b_approvals.py
?? backend/app/api/deps.py
?? backend/app/api/routes/auth.py
?? backend/app/core/security.py
?? backend/app/db/models/approval_decision.py
?? backend/app/db/models/auth_session.py
?? backend/app/schemas/auth.py
?? backend/app/services/approval.py
?? backend/scripts/seed_dev_users.py
?? backend/tests/test_phase5b.py
?? backend/tests/test_phase5b_postgres.py
?? claudex-loop/                                  (untouched)
?? docs/phase5b.md
?? docs/phase5b-validation.md
```

The repository was clean (only the pre-existing unrelated `frontend/src/App.jsx`
edit and the untouched `.codex/`/`claudex-loop/` directories) before this
session; every modified backend file above was changed by this session's work.

## Auth mechanism implemented

Local username/password over HTTPS-ready cookies (see `docs/phase5b.md`,
"Authentication"): Argon2id password hash in PostgreSQL → server-issued
opaque session token → SHA-256 of the token stored in `auth_sessions` →
HttpOnly `SameSite=Lax` cookie → server resolves the verified `User` on
every request via `app.api.deps`. No `X-User-ID` or similar header, no
client-supplied role, no hosted identity provider, no hard-coded bypass.

## Password/session security design

- `argon2.PasswordHasher()` (Type ID / Argon2id default) for
  `hash_password`/`verify_password`; verified in
  `test_password_plaintext_never_stored` that the stored hash never
  contains the raw password and starts with `$argon2id$`.
- Session tokens: `secrets.token_urlsafe(32)` (256 bits of entropy), never
  stored raw — only `hashlib.sha256(token).hexdigest()` is persisted.
- Login failure (unknown user vs. wrong password) returns the identical
  401/message either way — no username enumeration.
- `CORSMiddleware.allow_credentials` flipped to `True` (required for the
  cookie to round-trip at all); safe because `cors_origins` remains an
  explicit whitelist, never `"*"`.
- `SESSION_COOKIE_SECURE` defaults `False` for local http dev — documented
  as a live limitation, must be `True` behind real TLS.

## Role/permission model

`User.role` (existing column, unchanged type) now conventionally holds
`requester` (new default, was `viewer`), `reviewer`, or `admin`. Enforced
only by `app.api.deps.require_role`, which always reloads the role from the
database — never a DB `CHECK` constraint (deliberately: `users` had 0 rows,
so a constraint would have been safe, but roles are an app-level
authorization convention here, not a data-integrity invariant worth a hard
schema commitment yet).

## Database changes / migration

`0006_phase5b_approvals` (see `docs/phase5b.md`, "Database changes" for the
full column/constraint list): `users.password_hash` + role default change,
`governance_requests.requester_user_id`, new `auth_sessions` (mutable), new
`approval_decisions` (immutable ledger, two partial unique indexes, a
composite FK to `action_revisions`, PostgreSQL `before_update`/
`before_delete` trigger reusing Phase 5A's existing trigger function).

`alembic upgrade head` and `alembic check` both pass against the live
PostgreSQL database (`0006_phase5b_approvals (head)`, "No new upgrade
operations detected"). Downgrade-to-`0005`-and-back is exercised by
`test_phase5b_postgres.py::test_migration_downgrade_upgrade_and_metadata`
and passed.

## Approval-decision model

`app.db.models.ApprovalDecision`: one immutable row per decision event
(`APPROVE`/`REJECT`/`REVOKE`), binding `request_id`, `action_id`,
`action_revision_id`, `canonical_request_hash`, `canonical_proposal_hash`,
`approver_id`, `decision`, `decided_at`, `approval_purpose`,
`policy_version` (`governance-5b-v1`), `reviewer_comment`, `expires_at`,
and (REVOKE rows only) `revoked_decision_id`/`revoked_at`/`revoked_by`.

## Governance state changes

Phase 5A's `ActionRevision.governance_status` column remains DB-constrained
to always read `PENDING_REVIEW` — unchanged. `app.services.governance` adds
`_ledger_state` (reads the decision ledger) and widens
`get_governance_state`/`assert_release_allowed` to compute
`PENDING_REVIEW`/`APPROVED`/`REJECTED`/`REVOKED`/`EXPIRED` live from that
ledger, strictly as an additive extension: every Phase 5A test that never
creates a decision still observes exactly Phase 5A's original behavior
(`ReleaseNotAllowed` for anything but the one new `APPROVED` case). `/query`
replay (`_draft_response`) now also reports this live status instead of the
stale immutable column.

## Self-approval policy

Implemented exactly as specified: `requester_user_id == reviewer.id` →
denied; `requester_user_id IS NULL` (unauthenticated origin) → ALSO denied,
fail-closed, no bypass. Documented as a known limitation in
`docs/phase5b.md`. Verified at the unit level
(`test_self_approval_is_rejected`, `test_unverified_requester_fails_closed`)
and live (see "Real authenticated end-to-end approval result" below).

## Approval API contracts

See `docs/phase5b.md`, "Approval API" for the full table. Summary:
`POST /auth/{login,logout}`, `GET /auth/me`, `GET /approvals` (real,
role-gated; previously a permanent `[]`), `GET /approvals/{revision_id}`
(new), `POST /approvals/{revision_id}/decision` (new), `GET
/approvals/{revision_id}/release` (new). The legacy
`POST /approvals/{approval_id}` placeholder is unchanged.

## Exact revision/hash binding

`apply_decision` reloads the `ActionRevision` row with `FOR UPDATE`,
re-verifies `approval_purpose`/`policy_version`, and stamps the decision's
`canonical_request_hash`/`canonical_proposal_hash` from that fresh reload —
never from any caller input. `expected_revision_id` (optional, from the
client) can only cause an early 409 on mismatch; it can never substitute
for the path-parameter-derived, server-verified revision.

## Approve/reject/revoke behavior

Approve/reject require live state `PENDING_REVIEW`; revoke requires live
state `APPROVED`. A same-reviewer/same-decision retry is idempotent
(returns the existing row); a different reviewer/decision on an
already-decided revision is `409 Conflict`. Verified at the unit level and,
for real concurrency, against live PostgreSQL with two actual threads
(`test_phase5b_postgres.py::test_concurrent_approve_and_reject_one_wins`).

## Expiry behavior

`expires_at = decided_at + APPROVAL_VALIDITY_SECONDS` (default 24h,
provisional/configurable, documented as not an MRPL policy) stamped once on
APPROVE. `test_expired_approval_cannot_release` forces a row's `expires_at`
into the past via raw SQL (the ORM row itself is immutable) and confirms
`get_governance_state` returns `EXPIRED` and the release gate then fails
closed.

## Release enforcement

`assert_release_allowed` fails closed for anything but `APPROVED`
(unchanged exception type from Phase 5A, `ReleaseNotAllowed`); `GET
/approvals/{id}/release` is the only caller and never bypassed by another
code path. Verified: approved → release succeeds
(`test_approved_exact_revision_passes_release_check`, and live); rejected
→ denied (`test_reject_transitions_and_cannot_release`, and live); revoked
→ denied (`test_revoked_approval_cannot_release`); expired → denied
(`test_expired_approval_cannot_release`); revision A's approval cannot
release revision B (`test_approval_for_revision_a_cannot_release_revision_b`).

## Concurrency/idempotency design

A PostgreSQL row lock (`SELECT ... FOR UPDATE` on the revision) plus two
partial unique indexes (`(action_revision_id) WHERE decision IN
('APPROVE','REJECT')`, and `WHERE decision = 'REVOKE'`) plus
`INSERT ... ON CONFLICT DO NOTHING` plus a re-select of the actual winner —
the same pattern Phase 5A already established for `GovernanceRequest` rows,
applied to decisions. SQLite (test fixtures) enforces the same partial
unique indexes for logic correctness but makes no real concurrency claim;
the concurrency claim itself rests only on
`test_phase5b_postgres.py`'s real two-thread test against live PostgreSQL.

## Legacy Approval handling

Untouched: no migration, no read, no write, no authority — confirmed
unchanged behavior via `test_legacy_approval_is_not_an_authority` (still
passes verbatim) and the retained legacy placeholder route.

## Tests added

- `backend/tests/test_phase5b.py` — 34 tests: `ApprovalServiceTests` (20,
  direct service-level: password hashing, requester/self-approval/
  unverified-requester authorization, exact-revision/hash binding, changed-
  proposal-requires-new-review, revision-A-cannot-release-B, model
  `approved=true` has no authority, approve/reject/revoke transitions,
  expiry, duplicate-retry idempotency, terminal-decision immutability, no
  new tool capability) and `AuthHTTPTests` (14, real HTTP layer via
  `TestClient`: login/logout/me, forged-cookie rejection, role
  enforcement, client `approved`/`approver_id` rejected as 422, full
  approve-then-release round trip, self-approval and wrong-revision denial
  via HTTP).
- `backend/tests/test_phase5b_postgres.py` — 4 opt-in
  (`WORKBENCH_TEST_POSTGRES=1`) tests against real PostgreSQL in an
  isolated schema: real concurrent approve-vs-reject race (two threads),
  raw-SQL mutation of a decision rejected, a second terminal-decision row
  rejected directly at the database level (bypassing the service), and
  migration downgrade/upgrade/metadata check.
- `backend/scripts/seed_dev_users.py` — local-development-only seed script
  (two users, real Argon2id-hashed passwords) used for the live test below;
  not a test file, mirrors the existing `prepare_retrieval_eval.py`
  dev-seeding convention.

Existing tests updated (necessary consequences of implementing the real
endpoints Phase 5A had left as placeholders/expected-absent, not
weakenings): `test_phase5a.py`'s `TABLES` list (now includes `User`,
`AuthSession`, `ApprovalDecision`, required once `GovernanceRequest` gained
a `users.id` foreign key) and one assertion in
`test_client_authority_fields_are_rejected` (`POST
/approvals/{uuid4()}/decision` now correctly 401s instead of 404, since the
endpoint is real and requires authentication); `test_foundation.py`'s
`test_approvals` (`GET /approvals` unauthenticated now 401s instead of
returning `[]`) and `test_metadata_and_offline_migration` (table count
16 → 18 for the two new tables).

A genuine bug was found and fixed by this test suite, not hidden: `_ledger_state`
originally compared a naive SQLite-returned `expires_at` against an aware
`datetime.now(timezone.utc)` and raised `TypeError`; and `apply_decision`
originally raised `DecisionConflict` on ANY already-decided revision before
ever checking whether the retry was the same reviewer/decision (breaking
the idempotent-retry requirement). Both are fixed in
`app/services/governance.py` / `app/services/approval.py`.

## Test totals

| Suite | Result |
|---|---|
| `compileall` (app, alembic, scripts, tests) | PASS |
| Phase 5A deterministic (`test_phase5a.py`) | 30 passed |
| Phase 5A PostgreSQL opt-in | 3 passed |
| Phase 5B deterministic (`test_phase5b.py`) | 34 passed |
| Phase 5B PostgreSQL opt-in (`test_phase5b_postgres.py`) | 4 passed |
| `test_agents*.py` (Phase 4 specialist/orchestration regressions) | 140 passed |
| `test_agent_outputs.py`, `test_model_gateway.py`, `test_phase4_repair.py` | 15 + 39 + 12 passed |
| `test_knowledge.py`, `test_pid.py`, `test_hybrid.py`, `test_structured.py` (Phase 3 regressions) | included in full suite below, all passed |
| `test_evaluation_asset_guard.py` (benchmark hash guard) | included below, passed; benchmark assets unchanged |
| Full backend suite, default env | **350 discovered, 342 passed, 0 failed/errored, 8 skipped** (3 Phase 5A PG opt-in + 4 Phase 5B PG opt-in + 1 live-model opt-in) |
| Full backend suite, `WORKBENCH_TEST_POSTGRES=1` | **350 discovered, 349 passed, 0 failed/errored, 1 skipped** (live-model opt-in only) |
| Alembic upgrade/check (live PostgreSQL) | PASS, head `0006_phase5b_approvals` |
| Docker Compose config | PASS |
| Frontend build | PASS |
| Frontend lint | PASS |
| `git diff --check` | PASS |

The live-model `WORKBENCH_TEST_LIVE_MODEL=1` foundation test was not
re-run in this session (unchanged from the prior Phase 5A follow-up, where
it passed in 246.6s); the live governed flow was instead exercised directly
below, which is a strictly stronger real-model check.

## PostgreSQL live results

- `sovereign_workbench` database, live Docker container, already at
  `0006_phase5b_approvals` head before and after this session's test runs.
- `test_phase5b_postgres.py`'s real two-thread concurrent approve-vs-reject
  race against an isolated schema: exactly one of the two decisions
  committed; the loser observed `DecisionConflict`; exactly one row exists
  in `approval_decisions` for that revision afterward.
- Raw SQL `UPDATE`/`DELETE` against `approval_decisions` both raised
  (PostgreSQL trigger), matching Phase 5A's existing `action_revisions`/
  `governance_requests` immutability guarantee extended to the new table.
- A second `APPROVE`/`REJECT` row inserted directly (bypassing
  `apply_decision`) for an already-decided revision was rejected by the
  partial unique index itself — the database enforces "only one
  authoritative terminal decision," not only the application.

## Real authenticated end-to-end approval result

Using `backend/scripts/seed_dev_users.py`'s `dev_requester`
(`role=requester`) and `dev_reviewer` (`role=reviewer`), against the live
PostgreSQL/Qdrant/local-`qwen3.5:9b` stack (no hosted AI):

1. `POST /auth/login` as `dev_requester` → `200`, session cookie set.
2. `POST /query` (with that cookie) — `"What is the maintenance status and
   history of pump P-101A?"` — completed in 3m27s on this host's measured
   ~3.3 tok/s local-model throughput (see `docs/phase5a-validation.md` for
   that calibration; unchanged in this phase). Result: `HTTP 200`,
   `governance_status: "PENDING_REVIEW"`,
   `action_revision_id: "6aa99e53-b17f-50a5-8221-ca2032425fe7"`,
   `human_review_required: true`, `schema: "S4"`, real citations against
   real retrieved evidence (same corpus/query pattern validated in Phase 5A).
3. Verified in PostgreSQL: `governance_requests.requester_user_id` for this
   request equals `dev_requester`'s id — the AUTHENTICATED requester, not a
   claimed string.
4. Self-approval, attempted two ways, both denied:
   - HTTP, as `dev_requester` (still logged in): `POST
     /approvals/{revision_id}/decision` → `403` ("Not authorized for this
     action" — the role gate fires first, since `dev_requester` also isn't
     a reviewer).
   - Direct service call, bypassing the role gate specifically to exercise
     the self-approval check itself: `apply_decision(..., reviewer=<the
     same dev_requester User row>, decision="approve")` →
     `DecisionNotAllowed: "Self-approval is prohibited: the requester
     cannot review their own request"`.
5. `POST /auth/login` as `dev_reviewer` → `200`.
6. `GET /approvals` (as `dev_reviewer`) → `200`, list includes this exact
   `action_revision_id` (and, separately, the one pre-existing Phase 5A
   revision with `requester_user_id: null`, correctly listed too — listing
   is permissive, deciding is where the fail-closed check lives, per
   `docs/phase5b.md`).
7. `GET /approvals/{revision_id}` (as `dev_reviewer`) → `200`, full
   immutable proposal, evidence, and hashes.
8. Wrong-revision check: `POST /approvals/{revision_id}/decision` with a
   mismatched `expected_revision_id` → `409`, decision NOT recorded.
9. `POST /approvals/{revision_id}/decision {"decision": "approve",
   "reviewer_comment": "Reviewed live for Phase 5B acceptance"}` (as
   `dev_reviewer`) → `200`, `governance_status: "APPROVED"`.
10. `GET /approvals/{revision_id}/release` → `200`,
    `governance_status: "RELEASED"`.
11. Verified in PostgreSQL: `approval_decisions` row with
    `approver_id = dev_reviewer.id`, `decision = 'APPROVE'`,
    `approval_purpose = 'ADVISORY_DRAFT_REVIEW'`,
    `policy_version = 'governance-5b-v1'`, and
    `canonical_request_hash`/`canonical_proposal_hash` matching the
    revision's own stored hashes exactly.
12. Re-`POST /query` with the same `request_id` (replay) →
    `governance_status: "APPROVED"`, `human_review_required: false` — the
    live-computed state, not a stale `PENDING_REVIEW`.

## Security/bypass tests (all denied as required)

Client `approved=true`/`approver_id`/`role` on `/auth/login` or
`/approvals/.../decision` → `422` (schema `extra="forbid"`, never silently
dropped). Forged/garbage session cookie → `401`, never a fallback identity.
Unauthenticated decision/list/me → `401`. Requester role on the approvals
list/decision endpoints → `403`. Self-approval (verified/unverified
requester, both cases) → denied. Wrong `expected_revision_id` → `409`.
Model `approved=true`/`approval_status="approved"` in specialist output →
no effect on computed governance state (still `PENDING_REVIEW` until a
real decision exists). A second terminal decision (different reviewer or
different decision value) on an already-decided revision → `409`, never a
silent overwrite, confirmed both at the application layer and directly at
the PostgreSQL partial-unique-index layer.

## Files changed

See "Repository state after work" above for the exact list. New: 12 files
(`app/api/deps.py`, `app/api/routes/auth.py`, `app/core/security.py`,
`app/db/models/{approval_decision,auth_session}.py`, `app/schemas/auth.py`,
`app/services/approval.py`, `alembic/versions/0006_phase5b_approvals.py`,
`scripts/seed_dev_users.py`, `tests/test_phase5b{,_postgres}.py`,
`docs/phase5b{,-validation}.md`). Modified: 14 backend files + `README.md`
(one line noting Phase 5B alongside the existing Phase 5A line).
`frontend/src/App.jsx`, `.codex/`, `claudex-loop/` — not touched.

## Unresolved issues

- **Known, documented limitation (not a defect):** a governed revision
  created via an unauthenticated `/query` call has no verified requester
  and can therefore never be approved/rejected (fails closed by design —
  see "Self-approval policy"). The one pre-existing Phase 5A revision in
  this database is such a case and stays permanently unreviewable.
- `admin` currently behaves identically to `reviewer` everywhere — no
  admin-only action exists yet to differentiate them; left undifferentiated
  rather than inventing an unrequested elevated capability.
- `SESSION_COOKIE_SECURE=False` by default (local http dev only) — must be
  set `True` behind real TLS before any non-local deployment.
- No frontend approvals UI (explicitly out of scope for this phase).
- No BLOCKER/HIGH issues.

## Exact git status

See "Repository state after work" above (identical content, git-status form).

## Independent security audit repair — 2026-09-20 (Astra)

An independent audit ("Astra") found two HIGH-severity bypasses in the
implementation above. Both are repaired here. No commit was performed by
this repair; Phase 5C was not started; `frontend/src/App.jsx`, `.codex/`,
and `claudex-loop/` remain untouched.

### Finding 1 (HIGH): service-layer authorization was not authoritative

**Root cause:** `app.services.approval.apply_decision` never checked the
caller-supplied `reviewer`'s role itself -- it trusted that whoever called it
had already been role-gated by the HTTP layer's `require_role("reviewer",
"admin")` dependency (`app.api.deps`). A direct service call (bypassing HTTP
entirely) with an ordinary `requester`-role `User` object could approve --
and then release -- a governed recommendation that was not even that
requester's own request (self-approval prohibition never fires here, since
`requester_user_id != reviewer.id`).

**Repair:** `apply_decision` now reloads the authoritative `User` row by
`reviewer.id` from the database and denies (`DecisionNotAllowed("Only an
authorized reviewer or admin may decide a governed revision")`) unless its
freshly-loaded `role` is `reviewer` or `admin` -- before any other check,
including self-approval. The caller-supplied `reviewer` object's `.id`/
`.role` are never trusted as-is; only the fresh reload's `.role` decides.
This closes the gap for direct-service-call, forged-in-memory-object, and
any future caller that skips the HTTP layer, while leaving
`app.api.deps.require_role` in place as defense-in-depth at the HTTP
boundary (`app/api/routes/approvals.py`'s 403/404 mapping was extended to
recognize the new message, unchanged behavior since HTTP already blocks this
case earlier via `require_role`).

### Finding 2 (HIGH): release gate trusted ledger state, not the decision's own binding

**Root cause:** `app.services.governance.assert_release_allowed` only asked
`get_governance_state` whether the ledger computed to `APPROVED` (i.e.,
whether *an* APPROVE row exists, is not revoked, is not expired). It never
verified that the APPROVE row's own persisted `canonical_request_hash`/
`canonical_proposal_hash`/`approval_purpose`/`policy_version` actually match
the exact `ActionRevision` being released. A forged or corrupted APPROVE row
(e.g. inserted directly, bypassing `apply_decision`) with the right
`action_revision_id` but wrong hashes computed to `APPROVED` and released
successfully -- reproduced by the audit as "MISMATCHED DECISION HASH
RELEASE: RELEASED".

**Repair:** `assert_release_allowed` now, after the existing state check,
independently reloads both the `ActionRevision` and its winning APPROVE
`ApprovalDecision` row fresh from the database and fails closed
(`ReleaseNotAllowed`) unless ALL of the following hold: the decision's
`action_revision_id` equals the revision's `id`; `canonical_request_hash`
matches; `canonical_proposal_hash` matches; `approval_purpose` matches; the
revision's `policy_version` equals the expected `governance-5a-v1`; and the
decision's `policy_version` equals the expected `governance-5b-v1`. The
existence of an APPROVE row, or a computed `APPROVED` state label, is no
longer sufficient by itself. No Phase 5A/5B control was weakened: every
previously-passing release/deny case (approved, rejected, revoked, expired,
revision-A-cannot-release-B) still behaves identically, verified below.

### Regression tests added

- `backend/tests/test_phase5b.py` (`ApprovalServiceTests`, SQLite, +3):
  `test_ordinary_requester_cannot_approve_via_direct_service_call` (Finding
  1 -- a second, unrelated `requester`-role user denied by
  `apply_decision` directly), `test_mismatched_request_hash_denies_release`
  and `test_mismatched_proposal_hash_denies_release` (Finding 2 -- a
  directly-inserted APPROVE row with one hash forged to `"0"*64` denied by
  `assert_release_allowed`, despite `get_governance_state` still computing
  `APPROVED`).
- `backend/tests/test_phase5b_postgres.py` (real PostgreSQL, +2, opt-in
  `WORKBENCH_TEST_POSTGRES=1`):
  `test_ordinary_requester_cannot_approve_via_direct_service_call` and
  `test_mismatched_decision_hash_denies_release` -- the same two probes
  reproduced against the live database, the security-sensitive persistence
  path the audit specifically exercised.
- Already covered by existing tests (no new test needed, re-verified
  passing): wrong `action_revision_id` / revision-A-cannot-release-B
  (`test_approval_for_revision_a_cannot_release_revision_b`), valid
  authorized reviewer + exact hashes (`test_approved_exact_revision_passes_release_check`),
  self-approval (`test_self_approval_is_rejected`,
  `test_self_approval_denied_via_http`), revoked/expired/rejected
  (`test_revoked_approval_cannot_release`, `test_expired_approval_cannot_release`,
  `test_reject_transitions_and_cannot_release`).

### Test results after repair

| Suite | Result |
|---|---|
| `test_phase5b.py` (deterministic, SQLite) | 37 passed (34 original + 3 new) |
| `test_phase5b_postgres.py` (real PostgreSQL, opt-in) | 6 passed (4 original + 2 new) |
| `test_phase5a.py` + `test_phase5a_postgres.py` (regression) | 33 passed, 8 subtests passed -- unchanged, no weakening |
| Full backend suite, `WORKBENCH_TEST_POSTGRES=1` | 354 passed, 1 skipped (live-model opt-in only), 14 subtests passed |
| `alembic check` (live PostgreSQL, head `0006_phase5b_approvals`) | PASS, no new upgrade operations detected -- no migration needed, this was an application-logic-only repair |
| `git diff --check` | PASS (only pre-existing CRLF/LF autocrlf warnings, no actual whitespace errors) |
| Benchmark assets | Untouched |

### Files touched by this repair

Modified only: `backend/app/services/approval.py` (Finding 1),
`backend/app/services/governance.py` (Finding 2),
`backend/app/api/routes/approvals.py` (error-mapping consistency for the new
message; HTTP behavior unchanged), `backend/tests/test_phase5b.py`,
`backend/tests/test_phase5b_postgres.py` (regression tests), this file. No
migration, no schema change, no new file, no other Phase 5B file touched.
`frontend/src/App.jsx`, `.codex/`, `claudex-loop/` -- untouched, as required.
Nothing committed.

### Remaining BLOCKER/HIGH findings

None known, after repair and re-verification of both reported findings plus
full regression.

## Final verdict: **PHASE 5B COMPLETE** (as of the 2026-09-20 Astra repair, above)
