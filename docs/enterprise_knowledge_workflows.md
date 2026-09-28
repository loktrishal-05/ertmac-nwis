# Enterprise Knowledge and Verification Workflows (Phase C)

Phase C completes the existing Verified Knowledge Registry
(`app/services/verified_knowledge.py`) and knowledge-gap detection
(`app/services/knowledge_gaps.py`) as one enterprise workflow. It adds no second
registry, governance framework, approval system or checkpoint store. Verification
decisions stay on the Phase 5 approval ledger (`apply_decision`), and history
stays on the Phase 5C tamper-evident audit chain (tamper-evident, not
tamper-proof: `verify_chain` detects modification; it does not prevent it).

## Lifecycle

```
source/document evidence -> CANDIDATE -> (human verify) -> VERIFIED
VERIFIED -> (source/revision/scope/binding change) -> STALE -> successor CANDIDATE -> VERIFIED
CANDIDATE -> REVOKED        VERIFIED -> REVOKED        STALE -> REVOKED
```

| Transition | Who | Mechanism |
| --- | --- | --- |
| create CANDIDATE | requester, reviewer, admin | `POST /verified-knowledge` |
| CANDIDATE -> VERIFIED | reviewer/admin, never the creator | `POST /verified-knowledge/{id}/verify` (ledger APPROVE) |
| -> STALE | system (refresh/revalidate) or reviewer/admin | read-time `refresh`, `POST /verified-knowledge/revalidate`, `POST .../{id}/stale` |
| -> REVOKED | reviewer/admin | `POST .../{id}/revoke` (ledger REVOKE, or REJECT for a candidate) |
| re-verification | requester+ creates, a different reviewer/admin verifies | `POST /verified-knowledge` with `supersedes_id`, then `verify` |

REVOKED is terminal: it cannot be superseded or re-verified; submit a new
candidate instead. Every decision requires the reviewed `expected_content_hash`,
so a reviewer can only decide exactly the content they inspected. No model,
graph node or agent tool can create, verify, stale, revoke or resolve anything:
all registered agent tools are read-only (enforced by
`tests/test_durable_execution.py::ToolAllowlistTests`).

## RBAC

Existing roles only (`requester`, `reviewer`, `admin`).

- requester/operator: read internal knowledge, submit candidates and gaps; cannot verify, revoke, revalidate or close gaps.
- reviewer: verify, revoke, stale, revalidate, read audit history, assign/resolve/dismiss gaps.
- admin: everything a reviewer can.

Identity comes only from the server session cookie (`app/api/deps.py`). Routes
use `require_role`, and services re-read the stored role with a column-only
query (`authorize`, `apply_decision`), so an in-memory or client-supplied role is
never trusted. Self-approval is refused by the ledger; a gap's submitter cannot
resolve or dismiss their own gap.

## Verification record

Each transition appends one audit event whose payload records: `knowledge_id`,
`revision`, `content_hash`, `previous_status`, `status`, the actor's stored
`actor_role` (the actor id is the event's `actor_id`), `reason` (reviewer comment
or system cause), `origin`/`origin_reference`, `asset_scope`, `supersedes_id`,
and `sources` (document id, document version id, source revision, source SHA-256).
`verified_by`/`verified_at` on the row come from the ledger decision. Evidence
references stay in the row's `evidence` and the signed governance proposal.

## Staleness and source revision invalidation

`refresh` (run on every inspect, list, fast-path and pack read) re-resolves each
source chunk and marks the item STALE, with an audit event, when any of these
change: local source bytes, source hash, chunk content, version metadata or
revision, lifecycle status, classification/access scope, a newer document
version, the signed proposal binding, or the ledger approval. Reads therefore
fail closed: VERIFIED knowledge from an older source is never served.
`POST /verified-knowledge/revalidate[?document_id=]` (reviewer/admin) runs the
same check immediately after an ingestion or source change, so the registry and
audit chain show the invalidation without waiting for the next read.

## Re-verification and history

Re-verification creates a successor revision (`supersedes_id`, `revision+1`)
that re-resolves the current sources and gets its own governed approval
revision. Verifying the successor moves a still-VERIFIED predecessor to STALE
(`reason: superseded_by:<id>`). Earlier rows, their `verified_by/verified_at`,
ledger decisions and audit events are never modified.

`GET /verified-knowledge/{id}/history` (reviewer/admin, matching `/audit/log`
visibility; requesters see provenance fields on the item itself) returns the full revision lineage and
every audit event bound to those governed revisions in chain order: creation,
ledger decisions, verification, staleness, revocation and linked gap
resolutions, each with its `event_hash`.

## Knowledge gaps

Gaps keep their deterministic id (`canonical_hash(subject, gap_type)`). Gaps
detected by governed executions remain OPEN until reviewed; a review persists
them in `knowledge_gaps` from server-side run metadata only.

```
OPEN -> UNDER_REVIEW (assign to a reviewer/admin)
OPEN|UNDER_REVIEW -> RESOLVED (reviewer/admin + evidence)
OPEN|UNDER_REVIEW -> DISMISSED (reviewer/admin + reason)
```

- `GET /knowledge-gaps[?status=]`, `POST /knowledge-gaps` (submit),
  `POST /knowledge-gaps/{gap_id}/{assign|resolve|dismiss}`.
- Resolution requires a note plus either currently VERIFIED knowledge
  (`knowledge_id`) or a current, indexed, not-superseded document version
  (`document_version_id`). A generated answer, an unverified candidate or a note
  alone cannot resolve a gap.
- Each transition emits one `KNOWLEDGE_GAP_TRANSITION` event (previous/new status,
  actor role, reason, links). A resolution linked to knowledge is bound to that
  knowledge's governed revision, so it appears in the knowledge history.
- RESOLVED and DISMISSED are terminal. Duplicate submissions return the existing
  gap without a new event.

## Candidate origins

`origin` is one of `manual_submission`, `document_ingestion`, `operator_note`,
`maintenance_analysis`, `pid_evidence`, `knowledge_gap`, `query_execution`, with
an optional `origin_reference`. Operator-note and knowledge-gap references must
exist and be in scope. Origin is provenance only and never grants trust:
every candidate must still cite current, internal, non-OCR indexed document
chunks and pass human verification.

## Access scope

Knowledge and gaps are `internal` only, set by the server. `access_scope` is a
`Literal["internal"]` on candidates, and gap submissions have no scope field
(extra fields are rejected), so a client cannot widen scope. `asset_scope`
(equipment tags, unit/facility ids, document ids) is derived on the server from
the indexed chunks and can filter listings (`?equipment_tag=`); it records
applicability and does not grant access.

## Verified Fast Path and CAG

Only knowledge that is VERIFIED after `refresh`, has current ledger approval,
passes the static-informational eligibility gate and matches exactly may be
served by the Verified Fast Path. CAG packs require every member to be currently
VERIFIED with the pinned content hash and revision; a stale, revoked or changed
member marks the pack aggregate STALE and the pack falls back to normal RAG.
Source mutation, staleness, revocation and scope changes all invalidate reuse
through the same checks. Normal RAG safety is unchanged.

## Multimodal (B1) and maintenance (B2) rules

- P&ID/visual candidates cannot be sources: OCR-derived chunks are rejected at
  candidate creation. P&ID findings enter the workflow as gaps (for example
  `pid_identity_review`) or as `pid_evidence`-origin candidates that cite
  authoritative non-OCR documents and still need human verification.
- Maintenance/sensor hypotheses never become VERIFIED automatically. They can
  be submitted as gaps or `maintenance_analysis`-origin candidates with provenance.

## Durability

Verification, revocation and gap decisions are short, human-initiated,
single-transaction operations: the ledger decision, row change and audit event
commit together or not at all. A crash before commit leaves nothing; a replayed
request after commit is refused because the state already moved, so no
duplicate decision or event is written. These decisions are not graph work and
do not use A2 checkpoints; A2 continues to cover long-running graph executions,
whose read-only tools cannot mutate knowledge.

## Observability

Audit payloads carry the knowledge id, status transition, actor and stored role,
source revision and hash, asset scope, gap id, reason and timestamps. No prompts
or model reasoning are recorded.

## Migration

`0016_enterprise_knowledge` (after `0015_durable_execution`) adds
`verified_knowledge.origin`, `origin_reference` and `asset_scope`, the
`knowledge_gaps` table, and the `KNOWLEDGE_GAP_TRANSITION` audit event type.
Existing rows default to `manual_submission`. The downgrade refuses to drop gap
history.

## Limitations

- Source invalidation happens at read time plus the explicit revalidate sweep;
  ingestion does not trigger the sweep automatically.
- The revalidate sweep scans live knowledge linearly; add a source index if the
  registry grows large.
- Only the `internal` scope exists; there are no per-unit or per-asset access grants.
- "Request clarification" is expressed as a gap or a revocation with a reason;
  there is no separate clarification state.
- A resolved gap is not reopened automatically if its linked knowledge later goes
  STALE or REVOKED; the history shows both events.
