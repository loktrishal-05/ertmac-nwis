# Phase 3C — Validation

## Deterministic backend tests

```powershell
# backend/
.\.venv\Scripts\python.exe -m compileall -q app alembic scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pip check
```

Result: **71/71 tests pass** (the prior 50 Phase 0–3B2 tests, unchanged, plus
21 new Phase 3C tests in `tests/test_structured.py`). `alembic check` reports
no drift against the live database. `pip check` reports no broken
requirements — no new dependency was added; parsing uses the standard-library
`csv`/`io`/`statistics` modules only.

New tests cover, mirroring the existing per-phase test-file convention
(deterministic unit tests with no live database — `tests/test_structured.py`
follows the same `MemorySession`-fake-plus-`TestClient` pattern already used
in `tests/test_pid.py`, and adds a SQLite in-memory session for the read/query
endpoints, which need genuine multi-filter relational queries rather than a
single checksum lookup):

- path traversal / absolute-path / Windows-ADS / wrong-extension rejection
  for both `data/raw/maintenance` and `data/raw/sensors` roots, including a
  symlink-escape check
- CSV size and UTF-8 encoding validation
- equipment-tag normalization (`P204`/`P-204`/`p-204` collapse to one
  `Equipment` row; ambiguous spellings are never forced together)
- maintenance CSV parsing: required-header check, missing-tag row rejection,
  `maintenance_type` normalization + unrecognized-value warning,
  malformed-date/downtime-hours handling (stored `null` with a warning, row
  kept), exact-duplicate-row skipping
- sensor CSV parsing: required-header check, row rejection for missing
  identity/timestamp/value, quality/unit preservation exactly as given,
  conflicting-duplicate-timestamp warning
- deterministic feature computation against the spec's own worked example
  (`3.1, 3.3, 3.4, 3.5, 8.2` → `first_value=3.1`, `last_value=8.2`,
  `absolute_change=5.1`, `percentage_change≈164.5`)
- anomaly observations: threshold-exceeded/below, sudden-change,
  missing-samples, stale-sensor, and bad-quality only fire when their
  threshold was explicitly supplied; `relative_increase`/`relative_decrease`
  fire unconditionally on the trend alone
- **`test_no_observation_ever_names_a_diagnosis`** — asserts no anomaly
  observation string ever contains "bearing", "failure", "damage",
  "cavitation", "diagnos", or "impeller"
- idempotent re-ingestion and metadata-conflict detection for both CSV
  ingestion endpoints via the real FastAPI routes
- maintenance/sensor query filtering, ordering, and citation/provenance
  correctness (history by equipment/type/status/date-range, work-order
  lookup, sensor readings by equipment/tag/window, latest-per-tag, and the
  full `POST /sensors/features` response) against a SQLite in-memory session
  exercised through the real service functions and real API routes

`tests/test_foundation.py`'s `test_metadata_and_offline_migration` model/table
count was updated from 10 to 12 to reflect the two new models
(`StructuredDataSource`, `MaintenanceRecord`); the test's assertions
(offline-mode `alembic upgrade head` SQL contains every table, every table's
primary key is `id`) are otherwise unchanged and still pass.

## Live validation (real PostgreSQL)

```powershell
# repository root
docker compose -f infra/docker-compose.yml up -d --wait
docker compose -f infra/docker-compose.yml exec postgres pg_isready -U postgres -d sovereign_workbench
Invoke-RestMethod http://127.0.0.1:6333/healthz
# backend/
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m scripts.smoke_structured --fresh
```

`scripts/smoke_structured.py` follows the same opt-in pattern as
`smoke_knowledge.py`/`smoke_pid.py`: it creates small synthetic CSV fixtures
(only if they don't already exist — `--fresh` always creates a genuinely new,
uniquely-named and uniquely-dated pair of fixtures so a cached duplicate is
never mistaken for a fresh run), then drives the real FastAPI handlers
end-to-end against the configured PostgreSQL database.

Executed steps, matching the requested live-validation checklist exactly:

1. **PostgreSQL and Qdrant confirmed healthy** — `pg_isready` and
   `/healthz` both pass before the script runs.
2. **Backend health confirmed** — the script's first assertion is
   `GET /health` returning `{"status": "ok"}`.
3. **Ingest synthetic maintenance CSV** — `POST /data/maintenance/ingest`
   returns `status: "ingested"`, `row_count: 3` (three rows: `P-204`,
   `P204`, `p-204`, all the same equipment).
4. **Ingest synthetic sensor CSV** — `POST /data/sensors/ingest` returns
   `status: "ingested"`, `row_count: 6` (five `VIB-P204-01` vibration points
   plus one fixture-marker row used only to keep fresh/reusable fixture
   bytes distinct).
5. **Query P-204 maintenance** — `GET /maintenance/history?equipment_tag=P-204`
   returns this run's three records, `equipment_tag: "P-204"` on every one
   (confirming `P204`/`p-204` normalized into the same equipment identity).
6. **Query WO-7712** — `GET /maintenance/work-orders/WO-7712` returns this
   run's record with `maintenance_type: "corrective"`.
7. **Fetch P-204 sensor readings** — `GET /sensors/readings?equipment_tag=P-204&sensor_tag=VIB-P204-01`
   returns this run's five points.
8. **Compute a feature window** — `POST /sensors/features` over exactly this
   run's window returns `count: 5`, `first_value: 3.1`, `last_value: 8.2`,
   and a `relative_increase` observation — with no forbidden diagnostic
   wording anywhere in the response (checked verbatim).
9. **Verify source-row provenance** — every returned record's `citation`
   carries the actual `source_filename`, `source_sha256`, and
   `source_row_number`; the feature response's `provenance` list and
   `citation_label` are checked the same way.
10. **Ingest the files again and verify no duplication** — both endpoints
    return `status: "duplicate"` with the same `source_id`; the maintenance
    history and sensor readings counts are identical before and after the
    repeat call.
11. **Verify original SHA-256 unchanged** — both source files' SHA-256 is
    recomputed after the full run and asserted equal to the value computed
    before any request was made.

Confirmed by direct execution in this environment:

```text
=== independent --fresh run ===
Phase 3C smoke validation passed.
  maintenance ingest: ingested in 0.16s, 3 rows
  sensor ingest: ingested in 0.12s, 6 rows
  feature window observations: ['relative_increase']

=== reusable fixture, first run ===
Phase 3C smoke validation passed.
  maintenance ingest: ingested in 0.14s, 3 rows
  sensor ingest: ingested in 0.08s, 6 rows

=== reusable fixture, second run (separate process) ===
Phase 3C smoke validation passed.
  maintenance ingest: duplicate in 0.12s, 3 rows
  sensor ingest: duplicate in 0.03s, 6 rows
```

The reusable-fixture pair was run twice as two **separate process
invocations** (not just two calls inside one script run) specifically to
confirm idempotency survives across process restarts, matching how the
`structured_data_sources` table — not in-process state — is the actual source
of duplicate-detection truth.

Synthetic fixtures and their ingested rows are intentionally left in place
after the run, for inspection, matching the existing Phase 3A/3B1 smoke-test
convention (`data/raw/maintenance/work_orders/phase3c_synthetic_*.csv`,
`data/raw/sensors/faults/phase3c_synthetic_*.csv`).

## Phase 3A / 3B1 / 3B2 regression

```powershell
.\.venv\Scripts\python.exe -m scripts.smoke_knowledge
.\.venv\Scripts\python.exe -m scripts.smoke_pid --fresh
.\.venv\Scripts\python.exe -m scripts.smoke_hybrid
```

All three ran against the same live PostgreSQL/Qdrant after the Phase 3C
schema migration and code changes:

- **Phase 3A** (`smoke_knowledge`): exit 0 — PDF ingestion, embedding, and
  citation-ready retrieval still work; duplicate detection unaffected.
- **Phase 3B1** (`smoke_pid --fresh`): exit 0 — P&ID OCR processing, tagging,
  and artifact generation still work.
- **Phase 3B2** (`smoke_hybrid`): exit 0 — hybrid dense/sparse/RRF/reranked
  retrieval, the Qdrant dense-backup preservation check, and the sparse
  backfill idempotence check all still pass.

No Phase 0–3B2 endpoint, schema, or contract was modified; the Alembic
migration only creates two new tables and adds columns to the previously
unused `sensor_readings` table.

## Frontend / repository-wide checks

```powershell
# frontend/
npm run build
npm run lint
# repository root
git diff --check
docker compose -f infra/docker-compose.yml config --quiet
```

Frontend build and lint are unaffected (no frontend changes in this phase)
and both pass. `docker compose config --quiet` validates cleanly — no
`infra/docker-compose.yml` changes were needed for Phase 3C.
