# Phase 5A — governance domain and enforcement boundary

Phase 4 is accepted with conditions per the operator's instruction. This change
implements only 5A. It does not reopen specialist design or start 5B–5F.

## Implemented

- Immutable governed request bindings and proposal revisions.
- Deterministic backend policy and server-owned `PENDING_REVIEW` state.
- One common enforcement service after specialist validation in `/query`.
- Canonical request/proposal hashes, evidence provenance snapshots, and draft responses.

## Domain and database

`AgentAction` remains the stable proposal identity. The new `GovernanceRequest`
binds a request ID to that action, its original revision, canonical request,
request hash, and claimed requester context. `ActionRevision` binds the proposal
and evidence snapshot to the request/action, originating `AgentRun`, policy
version, risk category, approval purpose, creation timestamp, and pending state.
The existing `Agent` table holds one deterministic governance ownership record;
this is a persistence owner, not another model agent or tool.

Migration `0005_governance_revisions` follows `0004_agent_runs`. Foreign keys
bind request, action, request hash, initial revision, and originating run.
The initial-revision foreign key is deferred until transaction commit.
Unique identities/content constraints prevent duplicate revisions. PostgreSQL
also checks SHA-256 against the exact stored canonical text. Update/delete
triggers make both new tables immutable, including bulk/raw SQL writes.
ORM update/delete guards provide earlier errors. Apply Alembic migrations;
ORM `create_all` alone does not install the PostgreSQL triggers.

Editing proposal content, its evidence snapshot, or other bound proposal fields
creates a new revision under the same action and request. Its state is freshly
`PENDING_REVIEW`. Neither legacy `AgentAction.status` nor any Phase 2 `Approval`
row grants governance authority. Legacy approvals are not modified or migrated.

## Canonicalization

`workbench-json-v1` uses Python's standard JSON encoder with deterministic key
ordering, compact separators, and UTF-8. Its envelope includes the format version.
SHA-256 hashes the exact stored UTF-8 text. This is **not RFC 8785/JCS**.

- String-keyed dictionaries, lists, strings, booleans, null, integers, and finite
  floats are supported. Lists preserve order; strings preserve content.
- Integral floats normalize to integers, including negative zero to zero.
  Other finite floats use the standard JSON encoder's numeric representation.
- Aware datetime values normalize to UTC, six fractional digits, and `Z`.
  Naive datetimes, non-finite numbers, lone Unicode surrogates, non-string keys,
  sets, arbitrary objects, and other unsupported types are rejected.
- UUIDs become lowercase canonical strings. Timestamp strings already present
  inside specialist text remain strings; the serializer does not guess their meaning.

The request hash binds normalized query text, access scope, and claimed requester
context. The proposal hash binds route, validated specialist output (including
its original advisory fields), evidence/provenance snapshot, and warnings.
Run IDs and runtime timings are provenance, not material proposal content.
Fixed hash vectors and a stored-JSON roundtrip test pin this contract.

## Policy, states, and enforcement

`app/services/governance.py` supplies `evaluate_governance`, `create_revision`,
`get_governance_state`, `assert_release_allowed`, and the response/retry boundary.

The only exposed states are `INFORMATIONAL` and `PENDING_REVIEW`. Only pending
revisions are persisted; the database cannot represent `APPROVED` in 5A.
There are no approval transitions. `assert_release_allowed` loads stored state
and always denies release, including unknown IDs. Caller-submitted decisions,
user IDs, and legacy approval IDs cannot change that behavior.

Any earlier graph requirement, nested specialist requirement, or existing
non-informational action classification increases caution. False or informational
model labels cannot lower it. Backend policy independently governs all S4/S6/S7
assessments/recommendations and unknown output shapes. S1/S3 output also becomes
pending when the existing operational classifier or the additional change-verb
scan finds operational content. Validated S5 refusals remain informational unless
a prior requirement already applies. These text scans are conservative heuristics,
not proof of safety: even `INFORMATIONAL` is never permission or a release credential.
Governing whole assessment schemas deliberately favors review over recall tuning.

The authoritative path is:

`request context → existing graph → specialist validation → governance policy →
atomic revision/provenance persistence → pending draft or informational response`

The existing router remains model-assisted; 5A does not claim it is deterministic
or implement pre-routing Phase 5E guardrails. Governance is deterministic and
outside that model decision. Raw graph/service computations are advisory results,
not an alternate approval or release interface.

## API and retry contract

`/query` accepts optional `request_id` (UUID retry key) and `requester_reference`
(claimed context). All client authority fields remain forbidden by the request
schema, including `approved`, `approval_status`, and `human_approval_required`.

The backend constructs `governance_status`, `action_revision_id`,
`human_review_required`, `presentation`, canonical hashes/version, policy version,
and `evidence_binding_status`. Pending output has `presentation=DRAFT` and the
legacy top-level `human_approval_required=True`. Nested model approval/authority
fields are removed from the displayed specialist result; original content remains
in the immutable proposal snapshot for provenance. No `approved=true` field is
returned. Model classifications are not exposed as authoritative action classes.

For stable first-response/retry behavior, pending responses use the stored revision
and its originating run; route confidence/reasoning are null and response timings
are empty. Detailed run timings remain in normal tracing when enabled.
An informational response does not create an action/revision/approval record.

Clients should generate and retain a UUID request key **before** sending a
governed request, so a timeout can be retried. Reusing a committed governed key
with identical content/context replays the original draft without calling the
model. Different content/context with that key returns 409; use a new request ID.
No key means a new independent request, not content-based global deduplication.
Informational-only requests are not cached or given actionable approval records.

For concurrent governed requests, deterministic IDs, unique constraints,
`INSERT ... ON CONFLICT DO NOTHING`, and a PostgreSQL request-row lock converge
on the first committed draft, even if repeated inference produced different text.
Explicit backend revision creation can add a new pending revision for edited
content, while API retries remain pinned to the immutable initial revision.
Identical content under the same policy reuses a revision. The transaction commits
the action, request, run, and revision together; failures return no draft and roll
back. Optional tracing cannot disable the minimal originating-run record.
PostgreSQL concurrency must be verified with the opt-in tests, not inferred from SQLite.

## Identity, evidence, and future audit attachment

There is no verified authenticated principal or approver. Requester references
and access scopes are claimed provenance, not authenticated identity. Requests
may enter pending review but never become approved. Retry keys are not credentials;
5A does not introduce access-control or authenticated review claims.

Evidence identities, hashes, locators, OCR provenance, and available content are
captured in the proposal snapshot with `PENDING_INTEGRITY`. Binding that snapshot
does not verify the source artifacts or implement Phase 5D manifests.

Request/revision IDs, originating run, requester context, policy version, timestamp,
and pending status are attachment points for future `AuditLog` events. No competing
audit table or hash chain is introduced.

## Not implemented yet

- Authenticated approver identity and human approve/reject API (5B).
- Audit hash chain (5C).
- Cryptographic evidence integrity/manifests (5D).
- Pre-routing Phase 5E guardrails.
- Release workflow and later acceptance work.

The approval endpoints remain non-mutating placeholders. No plant-control tools,
SCADA/DCS writes, equipment commands, permit/LOTO overrides, isolation declarations,
hosted inference, or new model endpoints are introduced. Future approval cannot
create capabilities absent from the closed, read-only tool registry.
