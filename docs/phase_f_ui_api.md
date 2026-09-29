# Phase F Workbench frontend API contract

Base: auth commit `1e9012296839895ac477c82d2aeb2c80b4b2b734` (see Git parent for exact commit).
Scope: read projections of existing backend records. No new migration, decision route,
model invocation, frontend change, persistent cache, or lifecycle authority.

## Shared rules

All URLs below are relative to the backend origin. Send the existing HttpOnly session
cookie (`credentials: "include"` across the configured CORS origin). Never send a role
or user ID as an authorization claim.

- **Human**: requester, reviewer, admin. **Review**: reviewer/admin.
- Executions retain **owner/admin** access; a reviewer cannot inspect another user's execution.
- P&ID reads expose only internal documents whose version processing request is also internal.
- Authentication failure: 401; forbidden role/ownership: 403. UUID/type/range validation: 422.
- New paginated collections: `limit=50` (1–100), `offset=0` (0–10000).
  Stable ordering includes an ID tie-breaker. Offsets are live views, not immutable snapshots;
  reload from offset zero if records change between pages.
- Collection envelope: `{items: object[], sample_size: int, as_of: UTC datetime,
  limit: int, offset: int, has_more: bool, next_offset: int|null}`.
  Empty: `items=[]`, sample_size 0, has_more false.
- Existing array routes preserve arrays and add `X-As-Of`, `X-Sample-Size`,
  `X-Has-More`. These and knowledge continuation headers are CORS-exposed.
- Optional start/end filters use ISO timestamps, normalize naive timestamps to UTC,
  reject reversed/equal bounds and ranges over 366 days. Newly added filters are
  half-open `[start,end)`; existing sensor/maintenance histories retain inclusive end.
- Operational responses and images are `Cache-Control: no-store`.
- Null means unavailable/unrecorded, never a fabricated measurement. Zero counts describe
  an observed empty cohort only. Do not replace null with zero in charts.
- Reads never return raw graph checkpoints, tool result bodies, hidden prompts, or chain-of-thought.
  UI strings from evidence remain untrusted text and must be escaped by the frontend.

## Dashboard

**GET /bi/operational — Review.** Extends the existing route; no competing dashboard endpoint.
Parameters: `range=24h|7d|30d|custom` (default 7d). Custom requires both start and end;
presets reject explicit bounds. Maximum custom duration: 366 days.

Response:
- `as_of`, `window:{start,end,semantics}`, `advisory_only:true`, `sample_limit:1000`.
- `samples`: runs, executions, approvals, decisions, knowledge, knowledge_gaps, audit:
  each `{sample_size,truncated,limit,as_of}`; metadata adds missing_runs.
- `query_volume:{bucket:hour|day,points:[{at,count}],sample_size,source}`.
  At most 1000 newest persisted runs in the window; omitted buckets are not filled.
  Runs are attempts with stored traces, not all incoming HTTP queries.
- `model_routing:{counts:map|null,sample_size}`: recorded model selection, including
  qwen3.5:4b/qwen3.5:9b when present. Missing selection is not inferred from configuration.
- `escalations:{count:int|null,sample_size}`: only explicitly recorded boolean outcomes.
- `execution_status`, `approval_status`, `approval_outcomes`, `knowledge_lifecycle`,
  `knowledge_gap_status`, `evidence_sufficiency`, `audit_activity`:
  each `{counts:map|null,sample_size}`.
- `pending_approvals:{count,sample_size}`: current pending state within the created-in-window
  revision cohort; not an all-time backlog. Use /approvals for the current review queue.
- `approval_latency_seconds:{mean:number|null,sample_size}`: creation to APPROVE/REJECT
  decision for decisions made in the selected window; excludes revocations/invalid time pairs.
- `service_status:null`, `limitations:string[]`.

Status cohorts use creation time, decisions use decision time, audit uses occurrence time.
Status values are current persisted states, not historical snapshots. Knowledge status is
last validated state: use existing inspect/revalidate to check current source integrity.
Gap counts cover persisted review records; detected gaps not yet persisted remain available
in /knowledge-gaps. Each cohort has its own sample denominator. Truncation must be shown.

Reuse **GET /health** (process health), **GET /ready** (existing release readiness),
**GET /models/status** (local runtime probe), **GET /product/status** (Human; speech/integration
configuration and health). Preserve their existing schemas and unavailable/503 behavior.
No new status aggregation invents service availability.

Compatibility: the HTTP dashboard now uses this windowed schema. The original internal
industrial_bi.snapshot helper remains for existing integration consumers.

## Executions

**GET /executions — Human, owner/admin rows only.**
Parameters: limit, offset, start/end (creation time), optional status:
PENDING, RUNNING, WAITING_APPROVAL, COMPLETED, REJECTED, INTERRUPTED, FAILED.
Order: created_at descending, execution ID descending.

Each item:
`{execution_id,user_id,status,current_node,retry_class,resume_count,retry_count,
checkpoint_version,selected_model,execution_path,route,created_at,updated_at,revision,
governance_status,action_revision_id,waiting_approval,resume_available,
resume_requires_server_recheck:true,receipt_status_counts}`.
Route/governance/approval ID are null if absent. Owner is a verified user ID, not a claimed name.
Counts summarize persisted node/tool operations; no receipt bodies or query text are returned.

**GET /executions/{execution_id} — owner/admin.** Existing route, now an explicit safe read projection.
Parameters: limit/offset for the timeline. Same item plus as_of and
`timeline:Collection<{kind:node|tool|operation,node,tool,status,retry_class,attempts,
started_at,finished_at}>`, and timeline_semantics.
Timeline is ordered by operation start then stable operation key. It represents the latest
persisted receipt per operation, not a fabricated event per retry. attempts remains a count.
Raw response/checkpoint bodies are omitted from GET; existing start/resume responses are unchanged.
The existing abandoned-worker reconciliation remains in force.
Missing or inaccessible execution: 403, without disclosing existence.

Resume availability is a UI hint. Pending approval is never resumable until a real decision
exists. Terminal/fail-closed states and graph/model incompatibility suppress the hint.
Reuse **POST /executions/{id}/resume**; it rechecks all authorization/preflight/governance
conditions and locking. Read metadata grants no release or plant-action authority.

## Approvals

**GET /approvals — Review.** Existing array route.
Parameters: limit/offset, `view=pending|history|all` (default pending), optional
`status=PENDING_REVIEW|APPROVED|REJECTED|REVOKED|EXPIRED`, start/end (revision creation).
Newest revision first, stable ID tie-breaker. Pending excludes the reviewer's own requests,
preserving existing policy. History includes decided revisions, including expired/revoked.
Requester gets 403 even for history; their execution read carries their own approval state.

Item:
`{action_revision_id,request_id,requester_user_id,route,selected_model,configured_model,execution_id,
created_at,governance_status,action_class,governance_reason,policy_version,evidence_count,
decided_at,reviewer_id,decisions:[{decision_id,decision,decided_at,reviewer_id,expires_at}]}`.
action_class is the stored approval purpose; governance_reason is the stored risk category.
Evidence count is null if no immutable manifest exists; zero is a recorded empty manifest.
execution_id is null for non-durable governed requests. No guessed associations.
Decision timestamps/reviewer IDs are null while pending. selected_model comes only from recorded
execution metadata; configured_model is the separate run configuration, never a claimed model call.

Reuse **GET /approvals/{revision_id} — Review** for existing revision/evidence/citation
summaries and complete decision detail. Unknown ID: 404.
Reuse **POST /approvals/{revision_id}/decision — Review** unchanged, including self-approval
prevention, exact hashes, expiry, revocation, and evidence checks.
Reuse existing **GET /approvals/{revision_id}/release** only under its existing authorized,
audited release flow. Reading history never releases an advisory.

## P&ID

**GET /documents/pid — Human.** limit/offset; collection of actual P&ID versions, newest first.
Item: `{document_version_id,document_id,filename,title,revision,source_sha256,
processing_status,page_count,artifacts_available,created_at}`.
Unprocessed/missing artifacts retain their actual status, page_count null and
artifacts_available false. Other document types and restricted versions are excluded.

**GET /documents/pid/{version_id} — Human.**
Parameters: `page=1` (1–10), limit/offset for regions on that page.
Response: version summary, as_of, limitation, selected_page,
`pages:[{page,width,height,image_url}]`, `regions:Collection<Region>`.
Region contains the existing persisted P&ID evidence schema:
evidence_id, kind, source_filename/source_sha256, locator, document/version/region IDs,
revision, page, bbox (rendered pixel coordinates), OCR confidence/status, combined_text,
text_items (text, normalized_text, confidence, bbox, polygon, image dimensions,
category, candidate tags/status), visual_candidates (bbox/type/tag/confidence/uncertainty),
visual_model, ocr_region_hash, fusion, conflicts, human_review_required.
Paths are not accepted from the client; raw source/image filesystem URIs are omitted.
Vision-only regions have null OCR confidence, never a fabricated OCR score.
Fusion reuses current registry verification and provenance rules. Repeated tag lookups are shared
only within one read, never across users or requests. It does not invoke a model.
Legacy regions lacking fusion remain unverified and require review.

**GET /documents/pid/{version_id}/pages/{page}/image — Human.**
Serves only the bound version's rendered PNG as image/png, no-store, nosniff.
No arbitrary file parameter, original-upload serving, HTML or SVG.
Invalid IDs: 422. Unknown/inaccessible version or missing page: 404.
Missing/corrupt/inconsistent or stale detail artifacts: 409 with a generic error.
Manifest/source/region bindings, source hash and current-version checks reuse the evidence
loader. Files have read-size limits; path traversal, cross-version image paths and escaping
symlinks are rejected. List remains usable when processing has failed.

**Mandatory UI safety:** imagery/OCR/fusion does not prove valve state, isolation, LOTO,
permit state, startup/shutdown/process readiness, connectivity or topology.
Verified identity means documented tag identity only. Always display the returned limitation.
No OCR regions, confidence values or visual candidates are generated by these reads.
Existing admin-only process/index routes retain their roles.

## Maintenance and sensors

**GET /equipment — Human.** New bounded tag selector, limit/offset, optional q (normalized
tag prefix, max 100). Envelope items: id, equipment_tag, name, equipment_type, location.
Order: tag, ID. Inventory presence does not imply verified field identity.

**GET /sensors/channels — Human.** New metadata selector; required equipment_tag (1–100),
limit/offset. Envelope items: sensor_tag, measurement, unit, thresholds:null.
Distinct channel/type/unit combinations are preserved; inconsistent units are not merged.
Unknown equipment: empty. There is no stored threshold registry to fabricate defaults from.

Reuse:
| Method/endpoint | Parameters/body | Response / empty behavior |
|---|---|---|
| GET /sensors/readings | equipment_tag, sensor_tag, measurement, start/end, limit 1–2000 (default 200) | results: SensorReadingOut[]; empty [] |
| GET /sensors/latest | required equipment_tag, optional sensor_tag | results[]; bounded SQL selection of latest per channel; empty [] |
| POST /sensors/features | existing SensorFeatureRequest | feature summary, observations, warnings, provenance; unavailable statistics null |
| POST /sensors/intelligence | equipment_tag, start/end, optional rolling_window, per-channel thresholds, maintenance_lookback_days | existing SensorMaintenanceIntelligenceResponse |
| GET /maintenance/history | equipment_tag, work_order_id, maintenance_type, status, start/end, limit 1–2000 (default 50) | results: MaintenanceRecordOut[]; empty [] |
| GET /maintenance/work-orders/{id} | work order identifier | same bounded results[] |
| GET /operator-notes | equipment_tag | existing internal notes, hard bound 100 |

All are Human; ingestion remains admin-only. History order is deterministic under tied dates.
Readings retain source filename/hash/row provenance. Sensor/maintenance GET ranges now reject
invalid bounds. Existing B2 intelligence already provides channel metadata, threshold crossings,
excursion persistence, elapsed rate/change, maintenance temporal links, observations,
hypotheses, contradictory evidence and recommended verification in separate fields.
Supply a threshold only from reviewed evidence or explicit operator input; no channel threshold
means no threshold-based crossing/persistence claim. Temporal relationships are not causal claims.
Use /sensors/intelligence for bounded multi-channel analysis; do not invent a second analysis API.

## Knowledge and gaps

**GET /verified-knowledge — Human.** Existing array and lifecycle export schema.
q (exact normalized question, max 2000), status CANDIDATE|VERIFIED|STALE|REVOKED,
origin (max 40), equipment_tag (max 100), limit/offset.
Fields include knowledge_id, title/question/statement, evidence, source_snapshot,
content_hash, revision/supersedes_id, lifecycle_state, trust, timestamps, provenance, asset_scope.

A page scans at most 100 records in stable created_at/ID descending order and refreshes source
validity before filtering. A page may be empty and still have more matches later.
Follow **X-Next-Offset**, not result length, while X-Has-More is true.
X-Scan-Limit is 100. Status changes are not used to define the offset population.
This preserves existing stale detection and does not relax verification.

Reuse **GET /verified-knowledge/{id} — Human** for the refreshed item and
**GET /verified-knowledge/{id}/history — Review** for lineage and audit events.
History now caps lineage at 100 and events at 500, exposes as_of, limits and truncated.
Use /audit/log with knowledge_id for paginated events on a particular revision.
Existing unrecognized/out-of-scope knowledge errors remain 409. Reviewer identity/history
visibility follows the existing schema and role gate. No lifecycle mutation route changes.

**GET /knowledge-gaps — Human.** Existing array; status OPEN|UNDER_REVIEW|RESOLVED|DISMISSED,
limit/offset. Stable gap ID order within the existing bounded recent sample.
Combines at most 500 persisted recent review records with at most 500 detected IDs from the
latest 100 execution metadata records. Exact stored-state overlay prevents an older closed gap
being shown OPEN. Header X-Scan-Limit:1000; this is a recent working set, not all-time inventory.
Fields preserve gap_id, subject, gap_type, required_evidence, related_evidence, origin/reference,
status, assignee, resolver, resolution knowledge/document version, note and timestamps where
recorded. Unpersisted detected gaps have no fabricated creator/decision timestamps.
Empty status sample: []. Existing assign/resolve/dismiss routes and ownership rules are unchanged.

## Audit

**GET /audit/log — Review.** Existing array.
Parameters: limit=100 (1–500), before_sequence>=1 for descending keyset pagination,
start/end, event_type (max 60), user_id, execution_id, approval_id (action revision UUID),
knowledge_id. Filters compose with AND; time is occurrence time.
execution_id matches the persisted request_id binding or an explicitly recorded payload run_id;
no fabricated association for unrelated events.
knowledge_id selects that internal object's approval revision, not every historical successor.

Event: id, chain_id, sequence_number, occurred_at, actor_id/kind, event_type, request_id,
action_revision_id, decision_id, payload:{}, payload_redacted:true, canonical_payload_hash,
previous_hash, event_hash. Raw internal payloads are intentionally redacted from this explorer.
Stored audit rows/hashes are unchanged. Hashes are not recomputed over the redacted response.
Headers expose as-of, returned count, and has-more; next cursor is the last returned sequence.
Unknown filter UUIDs yield [] without disclosing object existence.

Reuse **GET /audit/verify — Review** for authoritative full-chain verification:
valid, chain_id, events_checked, first/last sequence, head hash and error location/type.
Paginated filtered rows alone do not establish chain validity. Tamper-evident, not tamper-proof.

## Validation and integration

No schema migration is introduced; baseline/head remains 0017_accounts_recovery.
Use the isolated compose project, existing auth release image, disposable PostgreSQL and a
Linux Git-bundle checkout. The source worktree mount is read-only; validation artifacts live
only in its dedicated volume. External networking is disabled.

Commands after populating /validation/repo from the auth bundle and copying backend changes:

```sh
python -m alembic -c backend/alembic.ini upgrade 0017_accounts_recovery
python -m alembic -c backend/alembic.ini upgrade head
python -m alembic -c backend/alembic.ini check
python -m unittest test_phase_f_ui_api test_advanced_c test_phase5b test_phase5c test_durable_execution test_multimodal_pid -v
WORKBENCH_TEST_POSTGRES=1 python -m unittest discover -s backend/tests -v
python -m scripts.frozen_integrity
```

Tests use synthetic data. No live SMTP/Google calls and no BLIND execution.
Validation results and commit are recorded in the delivery report.
