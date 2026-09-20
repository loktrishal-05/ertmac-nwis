# Phase 5B — authenticated human approval workflow

Phase 5A is accepted and committed. This change implements only 5B: a real,
locally-authenticated reviewer who can approve/reject/revoke the EXACT
immutable Phase 5A revision they inspected, and a fail-closed advisory
release gate. It does not implement 5C, 5D, 5E, or 5F.

## Implemented

- Local username/password authentication: Argon2id password hashes in
  PostgreSQL, server-issued opaque session tokens (only their SHA-256 is
  stored), an HttpOnly session cookie, and server-side session verification
  on every request. No client-trusted header, no hosted identity provider.
- Roles (`requester`, `reviewer`, `admin` — an app-level convention on the
  existing `User.role` column, not a DB CHECK constraint) enforced by
  backend dependencies (`app.api.deps.require_role`), never by client input.
- An immutable, append-only approval-decision ledger
  (`app.db.models.ApprovalDecision`) bound to the exact
  `action_revision_id` + `request_id` + hashes of the revision it decides.
- Self-approval prohibition, failing closed when the requester's identity
  cannot be established.
- A live-computed governance state machine layered on top of Phase 5A's
  immutable `PENDING_REVIEW` baseline: `PENDING_REVIEW → APPROVED →
  REVOKED`, `PENDING_REVIEW → REJECTED`, and `APPROVED → EXPIRED`.
- A fail-closed advisory release gate
  (`app.services.governance.assert_release_allowed`) and a
  `GET /approvals/{id}/release` endpoint that only ever hands back an
  already-generated advisory recommendation for human/operational
  consideration — never plant execution, never a new capability.
- Concurrency-safe decisions: a PostgreSQL partial unique index (mirrored,
  without the same guarantee, as a SQLite partial index for logic tests)
  ensures at most one terminal (APPROVE/REJECT) decision and at most one
  REVOKE decision can ever exist per revision, backed by a row lock on the
  revision during a decision attempt. Retries by the same reviewer with the
  same decision are idempotent; a losing concurrent attempt gets a 409, not
  a silently-discarded success.

## Authentication

`app/core/security.py` provides `hash_password`/`verify_password` (Argon2id,
via `argon2-cffi`, the modern reference implementation) and
`new_session_token`/`hash_session_token` (a `secrets.token_urlsafe(32)`
opaque token; only its SHA-256 is ever persisted in `auth_sessions`, so a
database read alone cannot impersonate a live session).

`POST /auth/login` verifies the password, creates an `auth_sessions` row
(`expires_at` = now + `SESSION_TTL_SECONDS`, default 8h), and sets an
HttpOnly, `SameSite=Lax` cookie (`workbench_session` by default,
`SESSION_COOKIE_NAME`). Unknown username and wrong password return the same
401 with the same message — no username enumeration. `POST /auth/logout`
revokes the current session (idempotent: no session, or an already-revoked
one, is a no-op 200) and clears the cookie. `GET /auth/me` returns the
verified principal or 401.

`app/api/deps.py`'s `get_optional_current_user`/`get_current_user` resolve
identity ONLY by hashing the cookie value and looking up a live,
non-revoked, non-expired `auth_sessions` row — never from a header, never
from the request body. `require_role(*roles)` 403s anyone whose
server-loaded `role` isn't in the allowed set. `CORSMiddleware.allow_credentials`
is now `True` (was `False` in Phase 5A) so the cookie round-trips at all;
this remains safe because `cors_origins` is an explicit whitelist, never
`"*"` — browsers refuse credentialed requests with a wildcard origin.

`SESSION_COOKIE_SECURE` defaults to `False` for local http development.
**Any real deployment behind TLS must set it to `True`** — a non-Secure
cookie is a live limitation of this local prototype, not a design goal.

## Roles / permissions

`User.role` is a plain string (unchanged type; default changed from the old
placeholder `"viewer"` to `"requester"`, since `users` had zero rows in this
database). Convention, enforced only by backend dependencies:

| Role | May |
|---|---|
| `requester` | Call `/query` (as before, and now optionally authenticated) |
| `reviewer` | List/inspect pending revisions, approve/reject/revoke, release |
| `admin` | Everything `reviewer` can; no additional Phase 5B capability is implemented yet (elevated admin-only actions are deferred to whichever later phase defines them) |

Nothing in the schema or database grants these roles authority by itself —
`app.api.deps` is the only enforcement point, and it always re-loads the
user's role from the database on every request.

## Self-approval policy

`GovernanceRequest.requester_user_id` (new, nullable) is set exactly once,
at `create_revision` time, from the AUTHENTICATED session resolved by
`/query`'s optional auth dependency — never from `requester_reference`
(still an unverified claimed string, unchanged from 5A) and never from any
request body field. `/query` remains callable without authentication
(informational answers are unaffected); an unauthenticated governed request
simply has `requester_user_id = NULL`.

**Policy (fails closed, no convenience bypass):** if
`requester_user_id == reviewer.id`, the decision is refused
("Self-approval is prohibited"). If `requester_user_id IS NULL` — the
revision's requester identity was never established — the decision is
ALSO refused, not silently allowed. **Known limitation:** a governed
revision created via an unauthenticated `/query` call can never be
reviewed. This is deliberate: there is no reliable way to rule out
self-approval without a verified requester, and the task explicitly calls
for failing closed here rather than assuming it's fine. The one Phase 5A
revision already in this database (created before Phase 5B existed) is
exactly such a case, and remains permanently unreviewable unless the same
query is resubmitted by an authenticated requester.

## Database changes / migration

`0006_phase5b_approvals` (follows `0005_governance_revisions`):

- `users` gains `password_hash` (nullable — an account with no hash simply
  cannot authenticate) and its `role` default changes to `"requester"`.
- `governance_requests` gains `requester_user_id` (nullable FK → `users.id`).
- New table `auth_sessions` (mutable — logout/expiry legitimately update
  `revoked_at`; this is NOT part of the immutable governance ledger).
- New table `approval_decisions` (immutable, same `before_update`/
  `before_delete` PostgreSQL trigger and ORM guard pattern as Phase 5A's
  `governance_requests`/`action_revisions`), with:
  - a composite FK on (`action_revision_id`, `request_id`) →
    `action_revisions` (`id`, `request_id`) — rejects "request A / approval
    B confusion" at the database level, not just in application code;
  - a `CHECK` binding `revoked_decision_id`/`revoked_at`/`revoked_by` to
    exist if and only if `decision = 'REVOKE'`;
  - a partial unique index on `action_revision_id` WHERE
    `decision IN ('APPROVE','REJECT')` (at most one terminal review
    decision) and a second partial unique index WHERE `decision = 'REVOKE'`
    (at most one revoke), both enforced by PostgreSQL under real
    concurrency (see `test_phase5b_postgres.py`).

`alembic upgrade head` / `alembic check` both pass against the live
PostgreSQL database; downgrade to `0005_governance_revisions` and back is
exercised by the opt-in PostgreSQL test.

## The approval-decision ledger, precisely

`ApprovalDecision` is one row per decision EVENT — never a mutated "status"
column, for the same reason `action_revisions.governance_status` is
DB-constrained to always read `PENDING_REVIEW`: Phase 5A already committed
to an append-only design, and Phase 5C's future audit chain needs exactly
this shape. A revision's CURRENT governance state is *computed*
(`app.services.governance._ledger_state`/`get_governance_state`) from the
ledger, never stored:

- No APPROVE/REJECT row yet → `PENDING_REVIEW`.
- A REJECT row → `REJECTED` (terminal).
- An APPROVE row, no REVOKE row, not expired → `APPROVED`.
- An APPROVE row, no REVOKE row, past its `expires_at` → `EXPIRED`.
- An APPROVE row plus a REVOKE row → `REVOKED` (terminal).

A REVOKE row's own `revoked_at`/`revoked_by` describe the revoke event
itself (who revoked it, when) and `revoked_decision_id` names the APPROVE
row it revokes — revoking never mutates that APPROVE row.

## Approval API

| Endpoint | Auth | Behavior |
|---|---|---|
| `POST /auth/login` | none | Verify credentials, issue session cookie |
| `POST /auth/logout` | none (idempotent) | Revoke current session, clear cookie |
| `GET /auth/me` | any authenticated user | Verified principal |
| `GET /approvals` | `reviewer`/`admin` | Pending revisions the caller did not themselves author |
| `GET /approvals/{revision_id}` | `reviewer`/`admin` | Exact immutable revision + its decision history |
| `POST /approvals/{revision_id}/decision` | `reviewer`/`admin` | `{"decision": "approve"\|"reject"\|"revoke", "reviewer_comment"?, "expected_revision_id"?}` — fails closed on any mismatch |
| `GET /approvals/{revision_id}/release` | any authenticated user | Fails closed unless currently `APPROVED`; response reports `governance_status: "RELEASED"` (a response label, not a new persisted ledger state) |
| `POST /approvals/{approval_id}` | none | **Unchanged legacy Phase 2 placeholder** (see below) |

`DecisionRequest` is `extra="forbid"`: a client-supplied `approved`,
`approver_id`, `role`, or any other authority-shaped field is a 422, not a
silently-ignored field. `expected_revision_id` is accepted only as an
optimistic-binding convenience for a client that already knows which
revision it expects — the server always re-derives the authoritative
revision from the path parameter and the database; a mismatch can only make
a decision fail, never succeed differently.

`GET /approvals/{revision_id}` and the `/query` replay path both now report
the LIVE computed `governance_status` (via `get_governance_state`), not the
immutable revision's own baseline column — so replaying a `/query` request
after approval correctly returns `APPROVED`, not a stale `PENDING_REVIEW`.

## Exact revision / hash verification

Before any decision, `app.services.approval.apply_decision`:

1. Reloads the `ActionRevision` row with `SELECT ... FOR UPDATE` (fresh from
   the database, locked for the transaction — never a caller-held object).
2. Loads its `GovernanceRequest` binding.
3. Re-verifies `approval_purpose == "ADVISORY_DRAFT_REVIEW"` and
   `policy_version == "governance-5a-v1"` (the values Phase 5A's own DB
   `CHECK` constraints already guarantee — this is defense in depth, never
   trusting "it must be fine because the schema says so" alone).
4. Computes the live state from the ledger and rejects any decision that
   doesn't fit the current state (see "Approve/reject/revoke" below).
5. Checks self-approval / unverified-requester as above.
6. Only then inserts a new decision row, copying `canonical_request_hash`/
   `canonical_proposal_hash` from the freshly reloaded revision — never from
   the caller, never from a stale in-memory object.

Nothing about a decision can be supplied by the client except which of
`approve`/`reject`/`revoke` is requested, an optional comment, and the
optional `expected_revision_id` binding check.

## Approve / reject / revoke

- **Approve/reject** require the live state to be `PENDING_REVIEW`. A
  same-reviewer, same-decision retry on an already-decided revision returns
  the existing decision unchanged (idempotent). A different
  reviewer/decision on an already-decided revision gets `409 Conflict` —
  the first committed decision always wins; nothing is silently overwritten.
- **Revoke** requires the live state to be `APPROVED` (never `REJECTED`,
  never `PENDING_REVIEW`) and may be performed by any `reviewer`/`admin`
  (not only the original approver) — the same role gate as approve/reject.

## Expiry (provisional, not an MRPL policy)

`APPROVAL_VALIDITY_SECONDS` (default 24h, `settings.approval_validity_seconds`)
is stamped as `expires_at = decided_at + validity` on every APPROVE row at
decision time (immutable thereafter, like every other Phase 5A/5B hash/
timestamp field). This default is an **operator-configurable placeholder**,
not a reviewed or approved production retention policy — set
`APPROVAL_VALIDITY_SECONDS` in `.env` to change it. An expired `APPROVED`
revision computes to `EXPIRED` and the release gate fails closed exactly as
it does for `REJECTED`/`REVOKED`.

## Release boundary

`assert_release_allowed` (Phase 5A: always denied; Phase 5B: allows exactly
one case) permits release only when the live computed state is `APPROVED`
— missing, `PENDING_REVIEW`, `REJECTED`, `REVOKED`, and `EXPIRED` all deny
it, with the same exception type (`ReleaseNotAllowed`) for every case. There
is no direct code path that mutates governance state or returns a released
advisory without going through this function; the `GET
/approvals/{id}/release` endpoint is the only caller. Release does not
create, grant, or imply SCADA/DCS/valve/start-stop/interlock-bypass/permit/
LOTO/isolation authority — it hands back exactly the same advisory content
`/query` already generated, now labeled `RELEASED` in the response only.

## Concurrency / idempotency

- **Decision race:** `apply_decision` locks the revision row (`FOR UPDATE`)
  and inserts via `INSERT ... ON CONFLICT DO NOTHING`, then re-reads the
  actual winning row. If the winner isn't this call's own reviewer+decision,
  it raises `DecisionConflict` (409) rather than reporting false success.
  Verified under real concurrent threads against PostgreSQL in
  `test_phase5b_postgres.py::test_concurrent_approve_and_reject_one_wins`
  (NOT inferred from SQLite — SQLite has no real row locking).
- **Duplicate retry:** the same reviewer resubmitting the same decision on
  an already-decided revision gets the existing row back unchanged, not an
  error and not a second row.
- **Stale/replayed decision:** a different reviewer or a different decision
  value on an already-decided revision is a 409, never a silent overwrite.
- **Edit after approval:** editing proposal content still creates a brand
  new `ActionRevision` (Phase 5A behavior, unchanged) with its own
  independent decision history; approving the OLD revision has no effect on
  the NEW one (`test_approval_for_revision_a_cannot_release_revision_b`).

## Legacy Approval handling

The Phase 2 `Approval` table/model is completely untouched: no migration
touches it, no Phase 5B code reads or writes it, and it grants no Phase 5B
authority (this was already true in Phase 5A;
`test_legacy_approval_is_not_an_authority` still passes unchanged). The
legacy placeholder route `POST /approvals/{approval_id}` (no `/decision`
suffix) is kept byte-for-byte and still always returns
`{"status": "not_implemented"}` — it is a dead, inert endpoint, retained
only so its existing path doesn't 404 for whatever historical reason it was
added. `GET /approvals` was the only legacy route actually repurposed (it
previously always returned `[]` unauthenticated); this is documented in
`docs/phase5b-validation.md` and in `test_foundation.py`.

## Audit compatibility (Phase 5C is NOT built here)

Every `ApprovalDecision` row already carries actor id (`approver_id`),
decision (`APPROVE`/`REJECT`/`REVOKE`), request/action/revision ids, both
hashes, policy version, and a timestamp — the exact fields a future
tamper-evident hash chain (`AuditLog.previous_hash`/`current_hash`, already
present but untouched in this phase) would need to chain over. No
`AuditLog` row is written by Phase 5B; no hash-chaining logic exists yet.

## Not implemented

- Phase 5C tamper-evident audit hash chain.
- Phase 5D cryptographic evidence integrity/manifests (`evidence_binding_status`
  remains honestly `PENDING_INTEGRITY`; approval never upgrades it, and
  never claims otherwise).
- Phase 5E deterministic pre-routing guardrails.
- Phase 5F final governance/security acceptance.
- Any plant-control write path, SCADA/DCS integration, or new tool beyond
  the existing seven read-only tools (verified unchanged by
  `test_approval_creates_no_new_tool_capability`).
- A frontend approvals UI (out of scope for this phase; only the CORS
  `allow_credentials` flip in `main.py` and the optional-auth passthrough in
  `/query` were the minimum backend changes needed for a future frontend to
  work at all — no `frontend/src/App.jsx` edit was made or needed).
- Admin-specific elevated actions beyond what `reviewer` can already do — no
  such action is defined yet, so `admin` currently behaves identically to
  `reviewer` in every implemented endpoint.
