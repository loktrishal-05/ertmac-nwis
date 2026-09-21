# Phase 5D — cryptographic evidence integrity

Phase 5A, 5B, and 5C are accepted and committed. This change implements only
5D: an immutable, cryptographically-hashed evidence manifest binding every
governed `ActionRevision` to the exact evidence snapshot used to produce it,
plus deterministic re-verification against live authoritative sources before
release. It does not implement 5E or 5F.

**Evidence INTEGRITY is not evidence CORRECTNESS, OCR confidence,
authorization, or plant-state truth.** A manifest only proves: "this is the
exact evidence content that was present when the revision was created, and
it still matches its source where re-verification is possible." It never
judges whether the evidence is factually right, whether OCR read a label
correctly, whether anyone was authorized to act on it, or the real state of
any valve/process. `test_ocr_integrity_does_not_imply_topology_or_confidence`
proves this concretely: a low-confidence, "ambiguous" OCR region still
passes integrity verification, and no manifest item ever carries a
topology/connectivity/isolation/valve-state field.

## Implemented

- `app.db.models.EvidenceManifest` / `EvidenceManifestItem`: an immutable,
  hash-bound manifest frozen exactly once per governed `ActionRevision`
  (one-to-one, DB-enforced), with per-item hashes for document chunks, P&ID
  OCR regions, maintenance/sensor CSV rows, and sensor feature windows.
- Deterministic canonicalization reused unchanged from Phase 5A/5C
  (`app.services.canonicalization.canonical_json`/`canonical_hash`) — no
  second hashing implementation.
- Freezing at governance time: every `create_revision` call (including
  direct test/service calls, not only `/query`) freezes a manifest in the
  SAME transaction as the revision, so a revision without a manifest is
  structurally impossible going forward.
- Deterministic re-verification (`app.services.evidence_integrity.verify_manifest`)
  that recomputes every hash from scratch and additionally re-checks live
  authoritative sources (`DocumentVersion.source_sha256`, the actual current
  `MaintenanceRecord`/`SensorReading` row) where re-verification is possible
  — catching evidence mutated in its source table *after* the manifest was
  frozen, which the manifest's own internal self-consistency cannot detect
  by itself.
- A mandatory, fail-closed evidence-integrity check added to
  `app.services.governance.assert_release_allowed`: approval validity alone
  is no longer sufficient for release.
- PostgreSQL immutability (trigger + hash-binding `CHECK`) for both new
  tables, matching the established Phase 5A/5B/5C pattern.
- Audit integration via the existing Phase 5C chain (no second audit
  system): `EVIDENCE_MANIFEST_CREATED`, `EVIDENCE_INTEGRITY_VERIFIED`,
  `EVIDENCE_INTEGRITY_FAILED`.
- Read-only API exposure: `evidence_binding_status` (live-computed),
  `evidence_manifest_id`, `evidence_manifest_hash`, and
  `evidence_item_summaries` (identifiers/hashes only, never raw content) on
  the existing `/approvals/{revision_id}` and `/approvals/{revision_id}/release`
  responses.

## Not implemented

- Proof that evidence *content* is semantically true (integrity is not
  correctness).
- Proof that OCR *interpretation* is correct (integrity is not OCR
  confidence, and never implies topology, connectivity, flow direction, or
  physical isolation).
- Phase 5E deterministic pre-routing guardrails.
- Phase 5F final governance/security acceptance.
- Any plant-control write path, SCADA/DCS integration, or new tool beyond
  the existing seven read-only tools (verified unchanged by
  `test_no_plant_control_capability_introduced`).
- Retroactive claims of integrity for evidence that predates this phase (see
  "Legacy evidence handling").
- A frontend evidence-integrity UI (out of scope; no `frontend/src/App.jsx`
  change was made or needed).

## Reuse, not duplication

`app.agents.evidence.EvidenceRef` (Phase 3A/3B2/3C) already carries rich,
deterministic provenance for every citation — `source_sha256`, `chunk_id`/
`region_id`/`source_row_number`, OCR confidence/status, and a deterministic
`evidence_id` (`make_evidence_id`, itself SHA-256-based). This list is
already embedded verbatim in `ActionRevision.canonical_proposal`, so Phase 5A
already detects any tampering *within a frozen revision's own snapshot*.
Phase 5D's real incremental value, confirmed by inspection before writing
any code, is exactly two things Phase 5A's proposal hash cannot provide by
itself: (1) a separate, per-item-hashed structure suitable for a reviewer to
inspect at a glance, and (2) **live re-verification against the
authoritative source tables**, which catches a source row mutated *after*
the revision was frozen — something a snapshot hash alone can never detect,
since it only proves internal self-consistency, not continued agreement
with reality.

The existing `source_sha256` columns already populated at ingestion time
(`DocumentVersion.source_sha256`, `MaintenanceRecord.source_sha256`,
`SensorReading.source_sha256`, `StructuredDataSource.source_sha256`, all via
`app.services.extraction.source_sha256`) are reused directly — Phase 5D
invents no new source-file hash. No per-chunk *content* hash or per-record
*content* hash existed anywhere before this phase; that is the one genuinely
new hash Phase 5D computes, once, at manifest-freeze time.

## Database changes / migration

`0008_phase5d_evidence_integrity` (follows `0007_phase5c_audit_chain`):
creates `evidence_manifests` and `evidence_manifest_items` (both immutable,
same `reject_*_mutation()` trigger pattern as every prior phase's tables,
plus a `canonical_manifest_hash`/`canonical_manifest` binding `CHECK` on the
manifest), and widens `audit_events.event_type`'s `CHECK` constraint to admit
the three new Phase 5D event types. No Phase 5A/5B/5C table structure is
otherwise touched. `alembic upgrade head`/`alembic check` both pass against
the live PostgreSQL database; downgrade-to-`0007`-and-back is exercised by
`test_phase5d_postgres.py::test_migration_downgrade_upgrade_and_metadata`.

Two real bugs were found and fixed during this work, not hidden:

1. The model declares `EvidenceManifest.action_revision_id` with both
   `unique=True` and `index=True`, which SQLAlchemy compiles as a named
   unique *index*; the first migration draft used a table-level
   `UniqueConstraint` instead, which `alembic check` correctly flagged as
   drift the first time it was applied to live PostgreSQL. Fixed to
   `op.create_index(..., unique=True)`, matching the model exactly.
2. `app.services.evidence_integrity`'s sensor-reading and maintenance-record
   field hashing initially passed raw, sometimes-naive `datetime` values
   into `canonical_hash` (which requires timezone-aware datetimes) and into
   a JSON-typed `provenance` column (which cannot serialize a raw
   `datetime` at all). Both are fixed: naive SQLite-returned datetimes are
   treated as UTC (the same documented workaround `app.services.governance`/
   `app.services.audit` already use), and `provenance`'s `window_start`/
   `window_end` are stored as ISO-8601 strings.

## Manifest / item schema

`EvidenceManifest` (table `evidence_manifests`): `id`, `action_revision_id`
(unique FK — one manifest per revision), `manifest_version` (fixed
`"phase5d-evidence-v1"`), `canonical_manifest` (the deterministic JSON text
that was hashed), `canonical_manifest_hash`, `item_count`, `integrity_status`
(a frozen `CHECK`-constrained constant, `"PENDING_INTEGRITY"` — see
"Integrity status" below for why this never changes).

`EvidenceManifestItem` (table `evidence_manifest_items`): `id`,
`manifest_id`, `item_index` (stable position — order is itself hashed),
`evidence_type` (one of `document_chunk`/`pid_region`/`csv_row`/
`sensor_window`, exactly `EvidenceRef.kind`'s values, reused not
reinvented), `evidence_id` (the existing `make_evidence_id` value),
`source_identifier` (a human-diagnosable locator string, never itself
security-bearing), `source_hash` (the original file's `source_sha256`,
reused from existing columns), `content_hash` (freshly computed from the
actual evidence content), `provenance` (structured locator metadata —
page/section/bbox/window bounds/record ids, never large raw blobs or
secrets), `canonical_item_hash` (binds all of the above together).

## Canonical hashing design

`canonical_item_hash = canonical_hash({manifest_version, evidence_type,
evidence_id, source_identifier, source_hash, content_hash, provenance})` —
every field the task requires, no more. `canonical_manifest_hash =
canonical_hash({manifest_version, action_revision_id, item_count, items: [{item_index,
evidence_type, evidence_id, canonical_item_hash}, ...]})` — item **order**
is part of the hashed envelope (a stable list, never re-sorted), so
reordering items changes the manifest hash even if no single item's own
content changed. `canonical_manifest` (the deterministic JSON text) is
stored verbatim so the PostgreSQL `CHECK` (and any offline verifier) can
confirm `canonical_manifest_hash` without reimplementing canonicalization —
the identical technique Phase 5A/5C already established.

No `repr()`; no dict-insertion-order dependence (`canonical_json` always
sorts keys); NaN/infinity rejected (inherited from `canonical_hash`);
timestamps are always explicit-timezone before hashing (`_aware_utc`
normalizes SQLite's naive-datetime quirk to UTC, mirroring
`app.services.governance`/`app.services.audit`'s identical documented
workaround — PostgreSQL never needs this).

## Document/RAG evidence binding

For `document_chunk`: `content_hash = canonical_hash(quote)` (the exact
cited excerpt already frozen in the `EvidenceRef`); `provenance` carries
`document_id`, `document_version_id`, `chunk_id`, `page_start`/`page_end`,
`section_path`, `bounding_boxes`, and the OCR-derived flags/confidence/status
if the chunk came from OCR. `source_hash` is the `EvidenceRef`'s own
`source_sha256` — the original document file's hash, never a mutable
document/chunk ID alone. Live re-verification: `DocumentVersion` is looked
up by `document_version_id` and its *current* `source_sha256` must still
equal the frozen `source_hash` — if the version row is gone, or the document
was silently re-ingested under the same version with different bytes, this
is `source_missing`/`source_content_changed` respectively (verified live
against real PostgreSQL in `test_phase5d_postgres.py::test_document_version_source_change_detected_live`).
No live re-fetch from Qdrant is attempted — Qdrant is not append-only/
immutable and re-verifying against it would add a fragile network
dependency the task does not require ("where re-verification is possible");
the original source file's hash is the authoritative signal available here.

## OCR / P&ID evidence binding

For `pid_region`: `content_hash = canonical_hash(combined_text)` (the exact
recognized text already frozen); `provenance` carries `document_id`,
`document_version_id`, `region_id`, `page`, `bbox`, `confidence`,
`ocr_status`. **OCR confidence and status are carried as investigation
metadata only — never folded into what makes the hash "pass."** A region
with `confidence=0.05` and `ocr_status="ambiguous"` verifies exactly as
cleanly as a `confidence=0.99` one, because integrity is a statement about
*content stability*, not *recognition quality*
(`test_ocr_integrity_does_not_imply_topology_or_confidence`). Live
re-verification is identical to `document_chunk` (same `DocumentVersion`
check). Nothing here proves, or attempts to prove, topology, valve state,
connectivity, or flow direction — those forbidden claims are not fields
this system produces at all, confirmed by asserting they never appear in
any item's `provenance`.

## Maintenance data binding

For `csv_row` evidence pointing at a maintenance record: since a bare
`csv_row` `EvidenceRef` only carries `(source_filename, source_sha256,
source_row_number)` — not which table it came from — the row is resolved by
its existing `UniqueConstraint(source_sha256, source_row_number)` key
(tried against `maintenance_records` first, then `sensor_readings`; the two
source files never collide in practice). `content_hash` is computed from
the record's actual normalized field values (`equipment_id`,
`raw_equipment_tag`, `work_order_id`, `maintenance_type`, `failure_mode`,
`maintenance_date`, `description`, `downtime_hours`, `parts_replaced`,
`technician_notes`, `status`, plus a versioned `normalization_version`
constant) — never only the row number, exactly per the task's explicit
requirement. Live re-verification re-loads the row by its database `id`
(stored in `provenance`) and recomputes the same field hash fresh; any
edit to the row is caught (`test_changed_maintenance_record_hash_changes`,
and the general `source_content_changed` path).

## Sensor evidence / window binding

For `sensor_window` evidence: the frozen `EvidenceRef.provenance` list (an
ORDERED list of `{source_filename, source_sha256, source_row_number}`
citations, one per reading in the window) is resolved reading-by-reading,
IN ORDER, into per-reading hashes (`equipment_id`, `sensor_tag`,
`sensor_type`, `value`, `unit`, `quality`, `timestamp`, normalization
version). The window's `content_hash` binds the full **ordered** list of
per-reading hashes plus the resolved `window_start`/`window_end` (derived
from the actual resolved readings' timestamps, not re-fetched from the
original tool call's request parameters, which are not available at
governance-freeze time) and the reading count. Reordering the same readings
changes the hash (`test_changed_window_order_manifest_changes`); mutating
any one reading's value after freezing is caught on re-verification
(`test_modified_sensor_reading_detected_on_reverify`); the original ordered
citation list itself is retained in `provenance` (small — a few dozen
identifiers, never raw sensor values) specifically so re-verification can
replay the exact same resolution later rather than compare only derived
summary statistics — tampering with the stored citation order is caught as
an `item_hash_mismatch` (`test_reordered_sensor_readings_detected_on_reverify`),
a strictly stronger detection than checking source content alone. This is
never hashed from "a loose query description" — only from the exact
resolved reading identities and values.

## ActionRevision integration

`app.services.governance.create_revision` calls
`app.services.evidence_integrity.freeze_manifest` immediately after
inserting the `ActionRevision` row, in the SAME transaction, for **every**
revision — including ones created by direct test/service calls, not only
through `/query`. This guarantees `assert_release_allowed`'s new mandatory
integrity check always has a manifest to check against; `ActionRevision`'s
own `evidence_binding_status` column remains the pre-existing frozen
`'PENDING_INTEGRITY'` constant (unchanged schema, unchanged `CHECK`) — see
"Integrity status" for why. `app.services.governance.govern_response`
additionally audits `EVIDENCE_MANIFEST_CREATED` (mandatory, same
transaction) right alongside its existing `GOVERNED_REVISION_CREATED` event,
but only on the genuine first-time creation path (a replayed `/query` never
double-audits, matching the Phase 5C precedent exactly).

## Verification service

`app.services.evidence_integrity.verify_manifest(session, revision_id)` —
deterministic Python, never an LLM. Reloads the manifest and every item
fresh, recomputes the manifest-level hash and every item-level hash from
each row's own stored columns, and — only once those match — re-verifies
each item against its live authoritative source where possible. Returns
`{valid, manifest_id, action_revision_id, item_count, items_checked,
first_error_item_index, error_type}`, stopping at the first inconsistency.
`error_type` vocabulary: `manifest_missing`, `manifest_hash_mismatch`,
`item_hash_mismatch`, `source_content_changed`, `source_missing`.

`app.services.evidence_integrity.get_evidence_integrity_status(session,
revision_id)` is the LIVE, always-recomputed status exposed in API
responses — never a cached flag: `VERIFIED` (manifest exists, verifies
clean), `FAILED` (manifest exists, verification failed), `LEGACY_UNVERIFIED`
(no manifest exists at all — a revision predating Phase 5D). It is
impossible for this function to return `VERIFIED` without `verify_manifest`
having actually just run and passed.

## Release enforcement

`app.services.governance.assert_release_allowed` now requires, in order:
(1) the existing Phase 5B approval-validity check, (2) the existing revision/
decision binding check, and (3), new in Phase 5D, `verify_manifest` returning
`valid: True` for this exact revision — raising `EvidenceIntegrityFailure`
(a `ReleaseNotAllowed` subclass, so every existing `except
ReleaseNotAllowed` handler keeps working unchanged) otherwise. On success,
`EVIDENCE_INTEGRITY_VERIFIED` is audited mandatorily in the same
transaction as the eventual `ADVISORY_RELEASE_SUCCESS`. The LLM never
decides any of this — `verify_manifest` is deterministic backend code
called only from this one gate.

## Audit integration

Reuses the existing Phase 5C chain exclusively — no second audit system.
`EVIDENCE_MANIFEST_CREATED` (mandatory, `govern_response`),
`EVIDENCE_INTEGRITY_VERIFIED` (mandatory, `assert_release_allowed`'s success
path), `EVIDENCE_INTEGRITY_FAILED` (best-effort, logged by
`app/api/routes/approvals.py`'s release-denial handler specifically when the
denial is an `EvidenceIntegrityFailure` rather than a plain approval-state
denial — matching the identical mandatory-vs-best-effort split Phase 5C
already established for `ADVISORY_RELEASE_DENIED`). No manifest content,
raw evidence text, or secret ever appears in an audit payload — only IDs,
counts, and a hash.

## Legacy evidence handling

Every revision going forward always has a manifest (frozen unconditionally
in `create_revision`), so `LEGACY_UNVERIFIED` in practice only describes a
revision that predates this migration and was never able to have one. That
status is never conflated with `VERIFIED` —
`test_legacy_unverified_not_mislabeled_verified` constructs exactly this
case (a revision whose manifest was removed) and confirms
`get_evidence_integrity_status` reports `LEGACY_UNVERIFIED`, explicitly
asserting it is *not* `"VERIFIED"`. No original hash is ever fabricated for
historical evidence that never had one.

## Failure behavior

Fails closed for release when the manifest is missing, corrupted (item or
manifest hash mismatch), the wrong manifest is substituted, or the live
source has drifted/disappeared — `EvidenceIntegrityFailure` in every case,
verified in `test_approved_corrupted_evidence_cannot_release`,
`test_approved_wrong_manifest_cannot_release`, and, against real PostgreSQL,
`test_approved_revision_denies_release_after_live_source_drift`.
Informational (non-governed) `/query` responses are entirely unaffected —
they never touch this gate at all.

## No plant control

Phase 5D introduces no SCADA/DCS write path, no equipment control, no valve
operation, no alarm/interlock change, no permit issuance, no LOTO
completion. `test_no_plant_control_capability_introduced` confirms the tool
registry is byte-for-byte unchanged (the same seven read-only tools) after
exercising the full create → approve → verify → release path.
