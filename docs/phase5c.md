# Phase 5C — tamper-evident audit chain

Phase 5A and 5B are accepted and committed. This change implements only 5C: a
deterministic, PostgreSQL-backed, hash-linked, append-only ledger of
security/governance events, and a deterministic verifier that detects
modification, deletion, insertion, reordering, and truncation. It does not
implement 5D, 5E, or 5F.

**TAMPER-EVIDENT, not tamper-proof.** The chain does not physically prevent
someone with raw database access from writing a bad row (a determined actor
with superuser DB access can always do that to any table); what it guarantees
is that such tampering is *detectable* by `app.services.audit.verify_chain`,
never silently invisible. The chain is also **not an authorization
mechanism** — it grants no governance authority. Phase 5A's `assert_release_allowed`
and Phase 5B's `apply_decision` role/self-approval checks remain the sole
authority for what may be approved or released; this phase only records that
those decisions happened.

## Implemented

- A versioned, append-only `audit_events` table (`app.db.models.AuditEvent`):
  each row binds `schema_version`, `chain_id`, `sequence_number`, its own
  `id` (event id), `occurred_at`, `actor_id`/`actor_kind`, `event_type`, the
  relevant `request_id`/`action_revision_id`/`decision_id`, a structured
  `payload`, `canonical_payload_hash`, `previous_hash`, and `event_hash`.
- Deterministic canonicalization and hashing
  (`app.services.canonicalization.canonical_json`/`canonical_hash`, reused
  unchanged from Phase 5A): sorted keys, no dict-insertion-order dependence,
  no `repr()`, NaN/infinity rejected, UUID/datetime normalized explicitly.
- A documented genesis representation, sequence/previous-hash chain linkage,
  and a deterministic backend verifier (`app.services.audit.verify_chain`) —
  never an LLM.
- PostgreSQL immutability: a trigger rejects `UPDATE`/`DELETE` on
  `audit_events` (and `audit_checkpoints`), and a `CHECK` constraint rejects
  any row whose `event_hash` doesn't match its own stored canonical text —
  both enforced even against a raw SQL statement bypassing the application.
- Row-locked (`SELECT ... FOR UPDATE`), transaction-scoped sequencing:
  concurrent appenders to the same chain are serialized through a single
  `audit_chain_heads` cursor row, verified under real concurrent PostgreSQL
  threads.
- Integration with Phase 5A/5B: governed-revision creation, approve/reject/
  revoke decisions, and advisory-release success are **mandatory,
  same-transaction, fail-closed** audit events. Login success/failure,
  authorization denial, and release denial are **best-effort** events (see
  "Atomic governance/audit behavior" below for exactly why the split).
- A read-only, role-gated API: `GET /audit/log` and `GET /audit/verify`
  (reviewer/admin only, matching the Phase 5B approvals list).
- A minimal local checkpoint concept (`app.db.models.AuditCheckpoint`,
  `app.services.audit.create_checkpoint`) — no external anchoring.

## Not implemented

- Phase 5D cryptographic evidence integrity/manifests.
- Phase 5E deterministic pre-routing guardrails.
- Phase 5F final governance/security acceptance.
- External/off-host audit anchoring (see "Chain checkpoint / anchor hook"
  below — a documented future hardening option, not built here).
- Any plant-control write path, SCADA/DCS integration, or new tool beyond
  the existing seven read-only tools (verified unchanged by
  `test_no_plant_control_capability_introduced`).
- A frontend audit-log UI (out of scope; no `frontend/src/App.jsx` change
  was made or needed).
- Retroactive hash-chaining of any pre-Phase-5C event. Nothing before this
  chain's genesis is claimed to be verified (see "Legacy audit data").

## Reuse, not duplication

The legacy Phase 2 `app.db.models.AuditLog` table (`GET /audit/log` used to
be a permanent placeholder returning `[]`) is a completely different,
never-hash-chained table with zero rows ever written to it by any code in
this repository (confirmed by inspection before writing any Phase 5C code).
It is left in place, untouched by the migration, and is never conflated with
`audit_events` — `verify_chain` only ever reads `audit_events`. `GET
/audit/log` is repurposed to serve the real Phase 5C chain instead of the
dead placeholder, the one genuinely reusable piece of "existing audit API
architecture" this repo had.

`app.services.canonicalization` (Phase 5A) is reused unchanged — no second
canonicalization implementation was written. The row-lock/`ON CONFLICT DO
NOTHING`/re-select pattern for serializing concurrent writers is the same
technique Phase 5A's `GovernanceRequest` and Phase 5B's `ApprovalDecision`
already established, applied here to `audit_chain_heads`.

## Event schema

`app.db.models.AuditEvent` (table `audit_events`):

| Column | Notes |
|---|---|
| `id` | The event's own id (PK). This IS "event_id" — no separate duplicate column. |
| `schema_version` | Fixed `"phase5c-audit-v1"` (`app.services.audit.SCHEMA_VERSION`), DB-constrained. |
| `chain_id` | Fixed `"workbench-governance-v1"` (`app.services.audit.CHAIN_ID`) in production; a test may use any string. |
| `sequence_number` | Monotonic per `chain_id`, starting at 1. `UNIQUE(chain_id, sequence_number)`. |
| `occurred_at` | App-computed (`datetime.now(timezone.utc)`) at append time, not a DB `server_default` — must be known before hashing. |
| `actor_id` / `actor_kind` | `actor_kind` is one of `user`/`system`/`anonymous` (DB-constrained); `actor_id` nullable, FK → `users.id`. |
| `event_type` | One of the 9 values in `app.db.models.audit_event.EVENT_TYPES` (DB-constrained) — a bounded, non-flooding vocabulary. |
| `request_id` / `action_revision_id` / `decision_id` | Nullable FKs to `governance_requests`/`action_revisions`/`approval_decisions`, set where applicable. |
| `payload` | Structured investigation metadata (JSON/JSONB). Never a password, token, or session secret. |
| `canonical_payload_hash` | `canonical_hash(payload)`. |
| `previous_hash` | The prior event's `event_hash`, or the chain's genesis value for sequence 1. |
| `canonical_event_json` | The exact deterministic text that was hashed to produce `event_hash` — stored verbatim so the DB `CHECK` (and any offline verifier) can confirm it without reimplementing canonicalization. |
| `event_hash` | `sha256(canonical_event_json)`. `UNIQUE`. |

`app.db.models.AuditChainHead` (table `audit_chain_heads`) — **mutable**,
**not part of the tamper-evident chain itself**: one row per `chain_id`
holding `next_sequence_number`/`head_hash`, locked via `SELECT ... FOR
UPDATE` to serialize appends. Its own integrity is never trusted by
`verify_chain`, which recomputes everything from the immutable
`audit_events` rows alone.

`app.db.models.AuditCheckpoint` (table `audit_checkpoints`) — append-only,
immutable, but also not part of the hash chain; see "Chain checkpoint /
anchor hook" below.

## Canonicalization / hash design

Reuses `app.services.canonicalization.canonical_json`/`canonical_hash`
byte-for-byte (Phase 5A's `CANONICALIZATION_VERSION = "workbench-json-v1"`
format: sorted keys, no whitespace, `ensure_ascii=False`, `allow_nan=False`,
explicit UUID/timezone-aware-datetime normalization, lone-surrogate
rejection). No `repr()` anywhere; no reliance on Python dict insertion order
(canonicalization always sorts keys explicitly).

`event_hash` is computed as `sha256(canonical_json(envelope))` where
`envelope` (see `app.services.audit._envelope`, the one documented, versioned
hash-input shape) is exactly:

```
{schema_version, chain_id, sequence_number, event_id, occurred_at,
 actor_id, actor_kind, event_type, request_id, action_revision_id,
 decision_id, canonical_payload_hash, previous_hash}
```

`canonical_payload_hash` is a nested hash of the event's own `payload` dict
(computed the same way) — a hash-of-hashes, so a large/arbitrary payload
never needs to be re-embedded whole inside the envelope hash. Arbitrary
payload values (UUID, datetime) are normalized to plain JSON-safe values via
`app.services.audit._json_safe` (a `json.dumps(..., default=str,
allow_nan=False)`/`json.loads` round trip) *before* hashing, so
`canonical_payload_hash` is stable across a JSONB storage round trip — it
never depends on Python object identity or type that PostgreSQL wouldn't
preserve.

Fixed deterministic test vectors: `test_phase5c.py::test_fixed_genesis_vector`
pins the exact genesis hash for `chain_id="workbench-governance-v1"`; Phase
5A's own `CanonicalizationTests.test_fixed_vectors` (unchanged, still
passing) already pins `canonical_hash`'s behavior generally.

## Genesis design

Event #1's `previous_hash` is not a stored placeholder row — it's a pure,
documented function of `chain_id` alone
(`app.services.audit._genesis_previous_hash`):

```python
canonical_hash({
    "schema_version": "phase5c-audit-v1",
    "genesis_marker": "PHASE5C_AUDIT_CHAIN_GENESIS",
    "chain_id": chain_id,
})
```

Anyone re-verifying the chain offline can recompute this exact value without
needing any database row to exist — there is nothing to trust about a
"genesis row" because there isn't one.

## Append / locking design

`app.services.audit.append_event` (the diagram from the task, implemented
literally):

1. `SELECT ... FOR UPDATE` the chain's single `audit_chain_heads` row
   (inserting it first via `ON CONFLICT DO NOTHING` if this is the chain's
   very first event) — this **locks/reads the chain head**.
2. Reads `next_sequence_number`/`head_hash` off that locked row — **allocates
   the next sequence** and the **previous_hash**.
3. Computes `canonical_payload_hash`, the envelope, `canonical_event_json`,
   and `event_hash` — **calculates the event_hash**.
4. `session.add(record)` and advances the head row's
   `next_sequence_number`/`head_hash` — **inserts the event**.
5. `session.flush()` (never commits — see "Atomic governance/audit behavior").
   The **caller** commits, together with whatever governance/approval state
   change this event describes.

A hash chain is inherently sequential: the lock on the head row is
*correct*, not merely a performance optimization — two concurrent appenders
to the same chain cannot both legitimately claim to know "the current head"
at once, so one must wait.

## Database immutability enforcement

A PostgreSQL trigger function `reject_audit_event_mutation()` (mirroring
Phase 5A/5B's `reject_governed_revision_mutation()` pattern, but with an
accurate message for this table) is attached `BEFORE UPDATE OR DELETE` on
both `audit_events` and `audit_checkpoints`. This is DB-level, not merely an
ORM convention: `test_phase5c_postgres.py::test_raw_sql_update_of_audit_event_denied`
and `test_raw_sql_delete_of_audit_event_denied` prove a raw `UPDATE`/`DELETE`
statement — bypassing `app.services.audit` and the ORM entirely — is
rejected.

A `CHECK (event_hash = encode(sha256(convert_to(canonical_event_json,
'UTF8')), 'hex'))` constraint (same technique as Phase 5A's
`canonical_proposal_hash` binding) additionally rejects a raw `INSERT` whose
`event_hash` doesn't match its own `canonical_event_json` text — defense in
depth beyond just blocking post-insert mutation.

What is **not** DB-enforced, and cannot be with a single-row `CHECK`
constraint (PostgreSQL `CHECK` cannot reference other rows): that a row's
`previous_hash` actually equals the *prior* row's `event_hash`. That
cross-row linkage is exactly what `verify_chain` checks — this is precisely
the "tamper-evident, not tamper-proof" distinction: the database prevents
silent in-place corruption of a stored row, but a sufficiently-privileged
attacker could still insert an internally-self-consistent forged row (or an
entire forged tail); `verify_chain` is what makes that detectable, and a
periodic checkpoint (below) is what makes even a fully-reforged tail
detectable against an independent prior reference.

Per-role PostgreSQL `GRANT`/`REVOKE` privilege separation (a distinct DB role
for "append-only, no UPDATE/DELETE grant") was considered and **not**
implemented: this repository's existing Phase 5A/5B migrations never
separated DB roles either (the application always connects as one
configured role), and introducing one now would be an unrelated
infrastructure change to `.env`/`docker-compose.yml` this phase's task did
not ask for. Documented here explicitly as a real, available future
hardening option rather than silently skipped.

## Governance/approval events integrated

| Event | Trigger point | Atomicity |
|---|---|---|
| `GOVERNED_REVISION_CREATED` | `app.services.governance.govern_response`, right after `create_revision` succeeds on a genuinely new `request_id` | Mandatory, same transaction as the revision |
| `LOGIN_SUCCESS` | `app.api.routes.auth.login`, after the `AuthSession` insert | Mandatory, same transaction as the session |
| `LOGIN_FAILURE` | `app.api.routes.auth.login`, on invalid credentials | Best-effort (see below) |
| `APPROVAL_DECISION_APPROVE`/`REJECT`/`REVOKE` | `app.services.approval.apply_decision`, only once `winner` is confirmed to be this call's own freshly-inserted decision (never on a losing race or an idempotent retry) | Mandatory, same transaction as the decision |
| `APPROVAL_AUTHORIZATION_DENIED` | `app.api.routes.approvals.decide_approval`, in the `DecisionNotAllowed` handler | Best-effort |
| `ADVISORY_RELEASE_SUCCESS` | `app.services.approval.release_advisory` | Mandatory, own transaction (release has no other DB write) |
| `ADVISORY_RELEASE_DENIED` | `app.api.routes.approvals.release_approval`, in the `ReleaseNotAllowed` handler | Best-effort |

Every mandatory event carries the correct `actor_id` (the authenticated
principal) and the relevant `request_id`/`action_revision_id`/`decision_id`
— verified explicitly in `test_phase5c.py` (e.g.
`test_approve_audited` asserts `decision_id` equals the actual inserted
decision's id, not a placeholder).

## Verification service

`app.services.audit.verify_chain(session, chain_id=...)` — deterministic
Python, never an LLM. Walks every event for `chain_id` in `sequence_number`
order, independently recomputing every hash from each row's own stored
columns, and stops at the first inconsistency. Returns:

```python
{"valid": bool, "chain_id": str, "events_checked": int,
 "first_sequence": int | None, "last_sequence": int | None,
 "head_hash": str | None, "first_error_sequence": int | None,
 "error_type": str | None}
```

`error_type` vocabulary: `sequence_gap`, `sequence_out_of_order`,
`duplicate_sequence_number`, `wrong_chain_id`, `previous_hash_mismatch`,
`payload_hash_mismatch`, `event_hash_mismatch`. `wrong_chain_id` is
distinguished from the generic `event_hash_mismatch` by parsing the row's own
stored `canonical_event_json` (the text that was actually hashed) and
comparing its embedded `chain_id` against the row's `chain_id` column — a
row whose hash was computed for a *different* chain than the column claims
is a chain splice, not merely "some field changed."

## API changes

| Endpoint | Auth | Behavior |
|---|---|---|
| `GET /audit/log?limit=100` | `reviewer`/`admin` | Most recent `audit_events` rows for the authoritative chain, `sequence_number DESC`, `limit` capped at 500. Replaces the old permanent `[]` placeholder. |
| `GET /audit/verify` | `reviewer`/`admin` | The `verify_chain()` result. |

Both are **read-only**: neither accepts `event_hash`, `previous_hash`,
`sequence_number`, `chain_id`, or any other authority-shaped field from a
client. `app.services.audit.append_event`'s own signature has no such
parameters either — `test_append_event_rejects_client_supplied_hash_fields`
confirms passing them raises `TypeError` (unexpected keyword argument), not
a silently-accepted-and-ignored value. Role-gating matches the Phase 5B
approvals list (`reviewer`/`admin` only) since audit content can reveal
governance/approval activity a plain `requester` should not see.

## Concurrency behavior

Verified under real concurrent PostgreSQL threads
(`test_phase5c_postgres.py::test_concurrent_appends_produce_unique_monotonic_sequence_and_one_chain`,
8 workers hammering the same fresh chain simultaneously): sequence numbers
come back as exactly `{1, 2, ..., 8}` (no duplicates, no gaps, no lost
writes), `verify_chain` reports the resulting chain fully `valid`, and the
`audit_chain_heads` cursor's final `next_sequence_number`/`head_hash` matches
`verify_chain`'s own independently-recomputed head — the pointer and the
chain it points at agree, but only the chain's own hashes are ever trusted.
**SQLite (test fixtures) is never used to validate this claim** — the
deterministic suite's `with_for_update()` calls are silently accepted but
compile to no lock on SQLite (matching Phase 5A/5B's own documented
limitation for `GovernanceRequest`/`ApprovalDecision`); only
`test_phase5c_postgres.py` exercises real row locking.

## Atomic governance/audit behavior

`app.services.audit.append_event` never commits — it only `flush()`es within
the caller's own transaction, and raises `AuditChainError` (wrapping DB
failures, chain-head conflicts, duplicate-sequence violations, and hash
calculation failures alike) on any problem. For a **mandatory** event (one
describing an actual state change: revision creation, a decision, a
release), the caller lets that exception propagate and roll back the SAME
transaction as the state change — so `apply_decision` succeeding while its
audit trail silently failed is structurally impossible; either both commit
or neither does.

For a **best-effort** event (login failure, an authorization/release
*denial* — nothing state-changing happened), the append happens in its own
small transaction, started only after the caller has already rolled back the
denied attempt, wrapped in `try/except Exception: pass`. This deliberately
does **not** fail closed: a denial-logging failure must never turn an
already-correct `401`/`403` into a spurious `500`, because nothing
authoritative was at stake in the first place — there is no governance state
to protect by refusing the response. This split (mandatory vs. best-effort)
is the concrete, load-bearing answer to "avoid: approval commits
successfully, audit append fails, system falsely appears fully audited" —
the one case that must never happen is guaranteed not to by sharing a single
transaction; the informational case is explicitly scoped out of that
guarantee, and documented as such rather than silently inconsistent.

## Chain checkpoint / anchor hook

`app.db.models.AuditCheckpoint` / `app.services.audit.create_checkpoint`: a
minimal, **local-only** snapshot of `(chain_id, sequence_number, head_hash,
created_at)`, append-only but not part of the hash chain itself — an
independent reference an operator (or a future automated job) can compare a
later `verify_chain` head against, to catch even a fully-reforged tail (one
where every row was replaced with an internally-consistent fake chain) that
`verify_chain` alone, run against only the live table, could not by itself
distinguish from genuine history.

**No external/off-host anchoring is implemented or claimed.** This phase
does not write a checkpoint hash to any external system, notarization
service, or blockchain, and does not claim independent third-party
verification. Documented here explicitly as a **future hardening option**:
periodically exporting a checkpoint's `head_hash` to off-host, operator-
controlled storage (a signed log shipped off the machine, a separate
air-gapped record, etc.) would let an operator detect even a full local
database compromise — this phase intentionally does not invent a cloud
dependency to do that.

## Legacy audit data

`app.db.models.AuditLog` (Phase 2) is never hash-chained, holds zero rows
written by any code in this repository, and is **not** retroactively claimed
to be verified history. `verify_chain` only ever queries `AuditEvent` — a
legacy `AuditLog` row (if one is ever manually inserted) is structurally
invisible to it, confirmed by
`test_phase5c.py::test_legacy_audit_log_is_not_chained_history` and, with a
real inserted row against real PostgreSQL JSONB,
`test_phase5c_postgres.py::test_legacy_audit_log_row_is_not_chained_history`.
The Phase 5C chain starts from its own documented genesis (above); nothing
before it is retroactively covered.

## No plant control

Phase 5C introduces no SCADA/DCS write path, no equipment control, no valve
operation, no alarm/interlock change, no permit issuance, no LOTO completion.
Audit records only *describe* application/governance events after the fact;
`test_no_plant_control_capability_introduced` confirms the tool registry is
byte-for-byte unchanged (still exactly the same seven read-only tools) after
exercising the full create → approve → release → audit path.
