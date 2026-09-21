# Phase 5D validation — 2026-09-21

**PHASE 5D acceptance: COMPLETE.** Built on the accepted, committed Phase 5A
(`c76282d`), Phase 5B (`c0addf0`), and Phase 5C (`3777638`). No commit or
staging was performed by this work. Phase 5E was not started.

## Repository baseline before work

- Branch `master`, HEAD `3777638` ("Phase 5C: add tamper-evident audit
  chain"), working tree clean except the pre-existing unrelated
  `frontend/src/App.jsx` modification and untracked `.codex/`/`claudex-loop/`
  — none of which this work touched.
- Reviewed `docs/phase5a.md`, `docs/phase5b.md`, `docs/phase5c.md`,
  `app.agents.evidence.EvidenceRef` and its four kinds/factory functions,
  `app.schemas.knowledge.ChunkMetadata`, `app.services.pid_indexing`,
  `app.db.models.{document,document_version,maintenance_record,sensor_reading}`,
  `app.schemas.structured.StructuredCitation`,
  `app.agents.tools.sensors.compute_sensor_features`,
  `app.services.extraction.source_sha256`, `app.db.models.action_revision`
  (confirming `evidence_binding_status` is a frozen `CHECK`-constrained
  constant, the same pattern as `governance_status`), and the exact current
  state of `app.services.governance`, `app.services.approval`, and
  `app.services.audit`/`app.db.models.audit_event` (confirming
  `EVENT_TYPES` is a Python tuple baked directly into a DB `CheckConstraint`
  string, meaning widening it requires an explicit migration, not just an
  autogenerate) before writing any code. A forked research pass additionally
  confirmed no per-chunk or per-record content hash existed anywhere prior
  to this phase — only whole-source-file hashes.

## Repository state after work (before any commit)

```
 M backend/app/api/routes/approvals.py
 M backend/app/db/models/__init__.py
 M backend/app/db/models/audit_event.py
 M backend/app/schemas/approval.py
 M backend/app/schemas/query.py
 M backend/app/services/approval.py
 M backend/app/services/governance.py
 M backend/tests/test_foundation.py
 M backend/tests/test_phase5a.py
 M backend/tests/test_phase5b.py
 M backend/tests/test_phase5c.py
 M frontend/src/App.jsx                          (pre-existing, untouched)
?? .codex/                                        (untouched)
?? backend/alembic/versions/0008_phase5d_evidence_integrity.py
?? backend/app/db/models/evidence_manifest.py
?? backend/app/services/evidence_integrity.py
?? backend/tests/test_phase5d.py
?? backend/tests/test_phase5d_postgres.py
?? claudex-loop/                                  (untouched)
?? docs/phase5d.md
?? docs/phase5d-validation.md
```

Only backend files listed above (plus this doc pair) were changed by this
session's work; `frontend/src/App.jsx`, `.codex/`, and `claudex-loop/` were
never staged, modified, reverted, or cleaned.

## Evidence-integrity architecture

See `docs/phase5d.md` in full. Summary: `app.db.models.EvidenceManifest`/
`EvidenceManifestItem` (immutable, hash-bound, one manifest per
`ActionRevision`), `app.services.evidence_integrity` (the only writer —
`freeze_manifest` — and the only verifier — `verify_manifest`, plus
`get_evidence_integrity_status`), wired into
`app.services.governance.create_revision` (freeze, unconditional, every
revision) and `assert_release_allowed` (mandatory pre-release check, new
`EvidenceIntegrityFailure` exception), `app.services.approval.revision_detail`
(read-only manifest/item summary exposure), and
`app/api/routes/approvals.py`'s release-denial handler (distinguishes
`EVIDENCE_INTEGRITY_FAILED` from a plain `ADVISORY_RELEASE_DENIED`).

## Database changes / migration

`0008_phase5d_evidence_integrity` (follows `0007_phase5c_audit_chain`):
creates `evidence_manifests` (unique-indexed on `action_revision_id`,
`canonical_manifest_hash`/`canonical_manifest` binding `CHECK`, frozen
`integrity_status` `CHECK`) and `evidence_manifest_items` (bounded
`evidence_type` `CHECK`, hash-length `CHECK`s, `UNIQUE(manifest_id,
item_index)`), a `reject_evidence_manifest_mutation()` trigger function
applied `BEFORE UPDATE OR DELETE` on both, and an `ALTER TABLE audit_events`
widening `event_type`'s `CHECK` constraint to add the three new Phase 5D
event types. No Phase 5A/5B/5C table is otherwise touched.

Two real bugs were found and fixed during this work, not hidden:

1. First migration draft used `sa.UniqueConstraint("action_revision_id")`,
   but the model's `unique=True, index=True` compiles to a named unique
   *index* — `alembic check` correctly flagged `remove_constraint`/
   `add_index` drift the first time it was applied to live PostgreSQL.
   Fixed to `op.create_index(..., unique=True)`; the partially-applied
   first attempt was rolled back (`alembic downgrade` to `0007`, pointer
   restored) before reapplying cleanly.
2. `evidence_integrity.py`'s sensor/maintenance field-hashing initially
   passed naive SQLite datetimes into `canonical_hash` (which requires
   timezone-aware values) and raw `datetime` objects into a JSON
   `provenance` column (unserializable). Both fixed: an `_aware_utc` helper
   (mirroring `app.services.governance`'s identical documented SQLite
   workaround) normalizes naive datetimes to UTC before hashing, and
   `provenance`'s `window_start`/`window_end` are stored as ISO-8601
   strings.

`alembic upgrade head`/`alembic check` both pass against the live
PostgreSQL database (`0008_phase5d_evidence_integrity (head)`, "No new
upgrade operations detected"); downgrade-to-`0007`-and-back is exercised by
`test_phase5d_postgres.py::test_migration_downgrade_upgrade_and_metadata`
(after truncating `audit_events` in that isolated test schema first, since
earlier tests in the same schema legitimately populated rows using the new
event types that would otherwise violate the narrower pre-5D `CHECK` on
downgrade — real, correct database behavior, not a migration defect,
documented inline in the test).

## Manifest/item schema

`EvidenceManifest`: `id`, `action_revision_id` (unique FK), `manifest_version`
(fixed `"phase5d-evidence-v1"`), `canonical_manifest`, `canonical_manifest_hash`,
`item_count`, `integrity_status` (frozen constant `"PENDING_INTEGRITY"`).
`EvidenceManifestItem`: `id`, `manifest_id`, `item_index`, `evidence_type`
(`document_chunk`/`pid_region`/`csv_row`/`sensor_window` — exactly
`EvidenceRef.kind`'s values), `evidence_id`, `source_identifier`,
`source_hash`, `content_hash`, `provenance` (JSON/JSONB), `canonical_item_hash`.
Full column rationale in `docs/phase5d.md`, "Manifest / item schema".

## Canonical hashing design

Reuses `app.services.canonicalization.canonical_json`/`canonical_hash`
(Phase 5A) byte-for-byte — no second implementation. Item hash binds
`{manifest_version, evidence_type, evidence_id, source_identifier,
source_hash, content_hash, provenance}`; manifest hash binds
`{manifest_version, action_revision_id, item_count, items: [{item_index,
evidence_type, evidence_id, canonical_item_hash}, ...]}` — item order is
part of the hashed envelope. No `repr()`; sorted keys; NaN/infinity
rejected; timestamps always explicit-timezone before hashing.

## Document/RAG evidence binding

`content_hash = canonical_hash(quote)` (the exact frozen cited excerpt);
`source_hash` reused from the existing `EvidenceRef.source_sha256` (itself
sourced from `DocumentVersion.source_sha256`, populated at ingestion by
`app.services.extraction.source_sha256`) — never a mutable document/chunk ID
alone. Live re-verification re-loads `DocumentVersion` by
`document_version_id` and compares its *current* `source_sha256` to the
frozen value.

## OCR binding

`content_hash = canonical_hash(combined_text)` (the exact frozen OCR text);
`provenance` carries `region_id`/`page`/`bbox`/`confidence`/`ocr_status` as
investigation metadata only — **never folded into hash validity**.
`test_ocr_integrity_does_not_imply_topology_or_confidence` constructs a
`confidence=0.05`, `ocr_status="ambiguous"` region and confirms it still
reports `VERIFIED`, and asserts no `topology`/`connectivity`/`isolated`/
`valve_state`/`flow_direction` key ever appears in any item's `provenance`.
Same `DocumentVersion` live re-verification as document chunks.

## Maintenance binding

A `csv_row` `EvidenceRef` (which doesn't say which table it came from) is
resolved via the existing `UniqueConstraint(source_sha256,
source_row_number)` key against `maintenance_records` first, then
`sensor_readings`. `content_hash` covers the record's actual normalized
field values (equipment/work-order/type/failure-mode/date/description/
downtime/parts/notes/status) plus a versioned `normalization_version`
constant — never only the row number. Live re-verification re-loads the row
by its database `id` and recomputes the same hash fresh.

## Sensor/window binding

The frozen `EvidenceRef.provenance` (an ORDERED list of per-reading
citations) is resolved reading-by-reading, in order, into per-reading
hashes (equipment/tag/type/value/unit/quality/timestamp + normalization
version); the window's `content_hash` binds the full ordered hash list plus
resolved `window_start`/`window_end` and reading count. The original
ordered citation list is retained in `provenance` specifically so
re-verification can replay the exact resolution later. Reordering changes
the hash; mutating any one reading is caught on re-verification.

## ActionRevision integration

`create_revision` calls `freeze_manifest` unconditionally, in the same
transaction as the `ActionRevision` insert, for every revision — including
ones created by direct service/test calls, not only `/query`. This was a
deliberate design necessity, not a stylistic choice: it guarantees
`assert_release_allowed`'s new mandatory check always has a manifest to
evaluate, so every pre-existing Phase 5A/5B/5C test that creates a revision
and later approves/releases it continues to work unmodified in substance
(only SQLite fixture `TABLES` lists needed the two new tables added, and
five Phase 5C audit-sequence assertions needed updating for the two new
audit events now interleaved — both mechanical consequences, not behavior
changes; see "Existing tests updated" below).
`ActionRevision.evidence_binding_status` itself is untouched (same frozen
`'PENDING_INTEGRITY'` `CHECK`, no migration needed for that table).
`govern_response` additionally audits `EVIDENCE_MANIFEST_CREATED` (mandatory)
only on genuine first-time creation, never on replay.

## Verification service

`verify_manifest` — deterministic Python only, never an LLM. Reloads
everything fresh, recomputes manifest- and item-level hashes, then
re-verifies each item against its live authoritative source where possible.
Returns `{valid, manifest_id, action_revision_id, item_count,
items_checked, first_error_item_index, error_type}`. `error_type`
vocabulary: `manifest_missing`, `manifest_hash_mismatch`,
`item_hash_mismatch`, `source_content_changed`, `source_missing`.
`get_evidence_integrity_status` is the always-live-recomputed status
(`VERIFIED`/`FAILED`/`LEGACY_UNVERIFIED`) exposed in API responses — never a
cached flag.

## Release enforcement

`assert_release_allowed` now requires approval validity AND revision/
decision binding AND `verify_manifest(...).valid` — raising
`EvidenceIntegrityFailure` (a `ReleaseNotAllowed` subclass) otherwise, so
every existing `except ReleaseNotAllowed` handler keeps working unchanged.
Verified: a valid, approved revision releases normally
(`test_approved_valid_integrity_can_release`); a corrupted item denies
release (`test_approved_corrupted_evidence_cannot_release`); a substituted/
corrupted manifest hash denies release
(`test_approved_wrong_manifest_cannot_release`); and, against real
PostgreSQL, a live source-file change after approval denies release
(`test_approved_revision_denies_release_after_live_source_drift`).

## Audit integration

`EVIDENCE_MANIFEST_CREATED` (mandatory, `govern_response`),
`EVIDENCE_INTEGRITY_VERIFIED` (mandatory, `assert_release_allowed`'s success
path), `EVIDENCE_INTEGRITY_FAILED` (best-effort, the release-denial route
handler) — all through the existing Phase 5C chain, no second audit system.
Verified via HTTP end-to-end
(`test_integrity_failure_denies_release_and_is_audited_via_http`): approve
→ corrupt an item → release denied 403 → `GET /audit/log` shows exactly one
`EVIDENCE_INTEGRITY_FAILED` row bound to the correct `action_revision_id`.
No manifest content, raw evidence text, or secret appears in any audit
payload — only IDs, counts, and hashes.

## Legacy evidence handling

Every revision going forward always has a manifest; `LEGACY_UNVERIFIED`
describes only a revision that predates this migration (simulated in tests
by removing a manifest after the fact) and is never conflated with
`VERIFIED` — `test_legacy_unverified_not_mislabeled_verified` explicitly
asserts the status is `LEGACY_UNVERIFIED` and is *not* `"VERIFIED"`. No
original hash is fabricated for historical evidence that never had one.

## Tests added

- `backend/tests/test_phase5d.py` — 28 tests: `EvidenceIntegrityTests` (26,
  direct service-level — all 6 hashing scenarios, all 4 binding scenarios,
  ORM-level immutability, all 5 verification scenarios, all 3 release
  scenarios, the OCR integrity-vs-confidence/topology distinction, both
  sensor reorder/modification scenarios, both audit scenarios, and the
  plant-control boundary check) and `EvidenceIntegrityHTTPTests` (2, real
  HTTP layer via `TestClient` — integrity-failure release denial with audit
  verification, and the revision-detail API's evidence-summary exposure
  with no raw content leakage).
- `backend/tests/test_phase5d_postgres.py` — 5 opt-in
  (`WORKBENCH_TEST_POSTGRES=1`) tests against real PostgreSQL in an
  isolated schema: raw SQL `UPDATE`/`DELETE` rejected by the trigger on
  both new tables, a real `DocumentVersion` source-content-change detected
  live, an approved revision denied release after live source drift
  (real PostgreSQL, real `DocumentVersion` row), and migration
  downgrade/upgrade/`check`.

Existing tests updated (necessary consequences of Phase 5D integration, not
weakenings): `test_phase5a.py`, `test_phase5b.py`, `test_phase5c.py`'s
SQLite `TABLES` fixture lists gained `EvidenceManifest`/`EvidenceManifestItem`
(needed once `create_revision` started freezing a manifest inside those same
tests' transactions); one `test_phase5a.py` synthetic evidence dict gained a
valid `kind` field (evidence is now always processed, where before an
untyped raw dict was accepted uncritically); five `test_phase5c.py`
audit-sequence assertions were updated to include the two new interleaved
Phase 5D events (`EVIDENCE_MANIFEST_CREATED` after every
`GOVERNED_REVISION_CREATED`; `EVIDENCE_INTEGRITY_VERIFIED` before every
`ADVISORY_RELEASE_SUCCESS`) — the underlying Phase 5C behavior itself is
unchanged, confirmed by every other Phase 5C assertion (including full
`verify_chain` validity) still passing verbatim; `test_foundation.py`'s
table/model count (21 → 23 for the two new Phase 5D tables).

## Test totals

| Suite | Result |
|---|---|
| `compileall` (app, alembic, scripts, tests) | PASS |
| Phase 5A (`test_phase5a.py` + PostgreSQL) | unchanged, all passing |
| Phase 5B (`test_phase5b.py` + PostgreSQL) | unchanged, all passing |
| Phase 5C (`test_phase5c.py` + PostgreSQL) | all passing (5 assertions updated for interleaved 5D audit events, no behavior change) |
| Phase 5D deterministic (`test_phase5d.py`) | **28 passed** |
| Phase 5D PostgreSQL opt-in (`test_phase5d_postgres.py`) | **5 passed** |
| Phase 4/4R, Phase 3 regressions | included below, all passed |
| `test_evaluation_asset_guard.py` (benchmark hash guard) | included below, passed; benchmark assets unchanged |
| Full backend suite, `WORKBENCH_TEST_POSTGRES=1` | **426 discovered, 425 passed, 0 failed/errored, 1 skipped** (live-model opt-in only, not re-run this session — unrelated to Phase 5D and already validated live in earlier phases) |
| Alembic upgrade/check (live PostgreSQL) | PASS, head `0008_phase5d_evidence_integrity` |
| Docker Compose config | PASS |
| Frontend build | PASS |
| Frontend lint | PASS |
| `git diff --check` | PASS (only pre-existing CRLF/LF autocrlf warnings, no actual whitespace errors) |

## Live PostgreSQL results

- `sovereign_workbench` database, live Docker container, at
  `0008_phase5d_evidence_integrity` head before and after this session's
  test runs (confirmed via `alembic current`/`alembic check`).
- Raw SQL `UPDATE`/`DELETE` against `evidence_manifests`/
  `evidence_manifest_items` both raised (PostgreSQL trigger), matching the
  same immutability guarantee every prior phase established, extended to
  the evidence manifest tables.
- A real `DocumentVersion` row's `source_sha256` was mutated directly via
  raw SQL after a revision referencing it was frozen and verified
  `VERIFIED`; re-verification correctly flipped to `FAILED` with
  `error_type: "source_content_changed"`.
- An approved revision's underlying `DocumentVersion` was drifted the same
  way after approval; `release_advisory` raised `EvidenceIntegrityFailure`
  — release denied live, against real data, not merely in a mock.
- Migration downgrade (to `0007_phase5c_audit_chain`) and re-upgrade both
  succeeded cleanly with no drift.

## Tampering/substitution results

Every one of the task's required scenarios is a passing, independently
verified test: same evidence → same hash; changed document chunk/OCR
text/OCR region/maintenance record/sensor reading → hash changes; changed
window order → manifest changes; manifest substitution (a revision's
manifest hash overwritten with another revision's) → detected as
`manifest_hash_mismatch`; revision A's manifest cannot satisfy revision B's
verification (distinct manifest rows, confirmed never cross-referenced);
changed evidence produces an entirely new revision/manifest binding rather
than silently reusing the old approval; corrupted item/manifest hash →
detected; missing manifest → detected and correctly labeled
`LEGACY_UNVERIFIED`, never `VERIFIED`; reordered/modified sensor readings →
detected on re-verification; and, against live PostgreSQL, a real source
document/row mutated after freezing → detected and release denied.

## Files changed

See "Repository state after work" above for the exact list. New: 5 files
(`app/db/models/evidence_manifest.py`, `app/services/evidence_integrity.py`,
`alembic/versions/0008_phase5d_evidence_integrity.py`,
`tests/test_phase5d.py`, `tests/test_phase5d_postgres.py`) plus this doc
pair. Modified: 11 backend files. `frontend/src/App.jsx`, `.codex/`,
`claudex-loop/` — not touched.

## Unresolved issues

- No BLOCKER/HIGH issues.
- Live re-verification for `document_chunk`/`pid_region` evidence checks
  only `DocumentVersion.source_sha256` continuity, not a live Qdrant
  re-fetch of the chunk itself (documented, intentional scope boundary —
  Qdrant is not append-only/immutable and re-verifying against it would add
  a fragile network dependency the task's "where re-verification is
  possible" qualifier does not require).
- Sensor-window `content_hash` binds the *resolved* window bounds (derived
  from the actual readings' timestamps), not the original tool call's
  requested `start`/`end` parameters, which are not available at
  governance-freeze time — documented as an intentional, honest scope
  decision in `docs/phase5d.md`.
- No frontend evidence-integrity UI (explicitly out of scope for this
  phase).

## Exact git status

See "Repository state after work" above (identical content, git-status form).

## Final verdict: **PHASE 5D COMPLETE**
