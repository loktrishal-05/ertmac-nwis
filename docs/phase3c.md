# Phase 3C — Sensor and maintenance structured-data pipeline

This phase extends the existing PostgreSQL/SQLAlchemy foundation with two CSV
ingestion pipelines and their read-only query APIs. It reuses the existing
`Equipment` table, extends the existing `SensorReading` table, and adds the
smallest new schema needed for maintenance history: one `maintenance_records`
table and one shared `structured_data_sources` table for file-level provenance
and idempotency (the CSV analogue of `document_versions`).

**Phase 3C generates no AI diagnoses.** Feature computation is deterministic
arithmetic (count, min, max, mean, median, stdev, first/last value, absolute
and percentage change, optional rolling mean/slope). Anomaly detection reports
factual observations — a value crossed a caller-supplied threshold, a value
changed suddenly, samples are missing, a reading is stale, a quality flag is
present, or the latest value increased/decreased relative to preceding values
in the window. **Sensor anomalies are observations, not diagnoses.** No
function anywhere in this phase names a failure mode ("bearing failure",
"cavitation", "impeller damage") — that inference belongs to a future
agent/reasoning layer with human review, not to this ingestion/query service.

No LangGraph, no agents, no Qwen/Ollama integration, and no Guardrail/HITL
workflow are added in this phase.

## Input directories

```text
data/raw/maintenance/{work_orders,equipment_master}/*.csv
data/raw/sensors/{normal,faults,tag_dictionary}/*.csv
```

Both ingestion endpoints accept any CSV directly under `data/raw/maintenance/`
or `data/raw/sensors/` respectively (including any subdirectory) — the
subdirectory name is organizational only and is not otherwise validated.
Public/synthetic data only; source bytes are read once, hashed, and never
mutated. Immutable byte snapshot → SHA-256 → deterministic row parsing →
normalization → PostgreSQL rows, mirroring the Phase 3A/3B1 provenance model.

## Database schema

Reused as-is: `Equipment` (`equipment_tag` unique, `name`, `equipment_type`,
`location`).

Extended: `SensorReading` gained `sensor_tag`, `quality`, `created_at`,
`source_filename`, `source_sha256`, `source_row_number`, and a unique
constraint on `(source_sha256, source_row_number)`. Its existing `sensor_type`
column is reused directly for the "measurement" concept (vibration,
bearing_temperature, pressure, flow, temperature, motor_current, speed, …) —
no duplicate column was added. `unit` became nullable (a reading may arrive
without a declared unit).

New: `maintenance_records` — `equipment_id` (FK), `raw_equipment_tag`,
`work_order_id`, `maintenance_type`, `failure_mode`, `maintenance_date`,
`description`, `downtime_hours`, `parts_replaced`, `technician_notes`,
`status`, `source_filename`, `source_sha256`, `source_row_number`, `raw_row`
(JSONB, the complete original CSV row for a field not otherwise modeled), and
a unique constraint on `(source_sha256, source_row_number)`.

New: `structured_data_sources` — one row per ingested CSV file:
`source_type` (`maintenance`|`sensor`), `source_filename`, `source_uri`,
`source_sha256` (unique), `status`, `row_count`, `rejected_row_count`,
`ingestion_metadata` (the request fields used for conflict detection),
`warnings`. This is the CSV analogue of `document_versions` and is what makes
re-ingestion of an unchanged file a cheap duplicate check instead of a
re-parse.

Migration: `0003_structured_data`. `alembic upgrade head` / `alembic check`
apply and verify cleanly against the existing database; no other Phase 0–3B2
table is touched.

## Equipment-tag normalization

Reuses the existing OCR/document identifier normalizer
(`app.services.pid_identifiers.normalize_identifier`: NFKC + dash-unification
+ uppercase) and conservatively extends it in
`app.services.equipment_tags.normalize_equipment_tag`: a bare `LETTER+DIGITS[+SUFFIX]`
shape matching the same letter-prefix vocabulary already used for equipment
tags (`P|V|E|C|T|R|K|M`) gets a dash inserted — `P204` → `P-204`. This means
`P204`, `P-204`, and `p-204` all resolve to the identical `Equipment` row.
Anything that does not exactly match that bare shape (`PUMP-204-MAIN`,
`XP101`) is left as-is: genuinely ambiguous spellings are never forced into a
guessed identity. `find_or_create_equipment` looks up the normalized tag and
creates a minimal `Equipment` row (`name=equipment_tag`,
`equipment_type="unknown"`) only when no matching row exists yet — it never
overwrites an equipment record supplied by another source.

## Maintenance CSV contract

Required header: `equipment_tag`. Everything else — `work_order_id`,
`maintenance_type`, `failure_mode`, `maintenance_date`, `description`,
`downtime_hours`, `parts_replaced`, `technician_notes`, `status` — is
optional, matching the "must not require every optional field" requirement.

Row handling:
- Missing `equipment_tag` → the row is rejected (counted in
  `rejected_row_count`, not stored).
- `maintenance_type` is lowercased; if not one of `preventive`, `corrective`,
  `inspection`, `overhaul` it is still stored as given, with a warning —
  unrecognized values are not treated as file-level errors.
- `maintenance_date` and `downtime_hours` that fail to parse are stored as
  `null` with a row warning naming the original text; the row is **not**
  dropped, since the rest of the row (description, work order, parts) can
  still be valid evidence.
- An exact duplicate row (identical raw CSV fields) is skipped with a
  warning; a differently-normalized `equipment_tag` (`P204` vs `P-204`) is
  not treated as a duplicate of a different row.
- `raw_row` preserves the complete original CSV row as JSONB, regardless of
  which typed columns were populated.

## Sensor CSV contract

Required headers: `timestamp`, `equipment_tag`, `sensor_tag`, `measurement`,
`value`. Optional: `unit`, `quality`.

Row handling:
- A row missing `equipment_tag`, `sensor_tag`, `measurement`, a parseable
  `timestamp` (ISO-8601, `Z` accepted), or a finite numeric `value` is
  rejected — a time-series point without those cannot be interpreted, and no
  measurement is ever guessed.
- `unit` is stored exactly as given, with **no unit conversion** — this is a
  deliberate decision to avoid inventing a conversion the source didn't
  state.
- `quality` is stored exactly as given (lowercased) when present; when
  absent it is `null`, never defaulted to `"good"`.
- An exact duplicate row is skipped. Two rows with the *same*
  equipment/sensor/timestamp but a *different* value are both retained with a
  "conflicting reading" warning — the pipeline does not guess which one is
  correct.
- `SensorReading.sensor_type` stores the lowercased `measurement` value; no
  fixed enum is enforced, so equipment can carry any sensor type without a
  schema change (`Do NOT hard-code assumptions that all equipment has all
  sensors` is honored by construction — nothing here assumes a sensor exists
  for a given equipment/measurement pair unless a row says so).

## Idempotency and conflict handling

Both `POST /data/maintenance/ingest` and `POST /data/sensors/ingest` follow
the same pattern as Phase 3A/3B1 ingestion: a PostgreSQL advisory transaction
lock on the source SHA-256 serializes concurrent identical submissions, and a
`structured_data_sources` row keyed on that SHA-256 is the durable
duplicate-detection record.

- Same bytes, same declared metadata (`facility_id`, `synthetic`) → `200`
  with `status: "duplicate"`; no rows are re-inserted, no re-parse happens.
- Same bytes, different metadata, or previously registered under the other
  ingestion domain (maintenance vs. sensor) → `409 Conflict`; the original
  record is untouched.
- Changed bytes under the same filename → a new, independent
  `structured_data_sources` row and a fresh set of `MaintenanceRecord` /
  `SensorReading` rows (there is no revision-grouping concept for CSVs, only
  content-hash identity).

## Sensor feature computation

`app.services.sensor_features.compute_features` is a pure function (no
database access) over a plain list of floats: `count`, `minimum`, `maximum`,
`mean`, `median`, `stdev` (population stdev), `first_value`, `last_value`,
`absolute_change`, `percentage_change`, and optional `rolling_mean` /
linear-regression `slope` when a `rolling_window` is requested. For the
spec's own worked example — vibration readings `3.1, 3.3, 3.4, 3.5, 8.2` —
this reports `first_value=3.1`, `last_value=8.2`, `absolute_change=5.1`,
`percentage_change≈164.5`, with **no** interpretation beyond those numbers.

## Anomaly observations

`app.services.sensor_features.detect_anomalies` only ever reports what was
measured against what was configured:

- `threshold_exceeded` / `threshold_below` — only when `thresholds.maximum` /
  `thresholds.minimum` is explicitly supplied in the request. No default
  engineering threshold (e.g. a vibration alert value) is ever built in;
  those are refinery/asset-specific facts that must come from the caller, a
  future stored per-asset limit, or an evaluation fixture — never invented
  here.
- `sudden_change` — only when `thresholds.max_absolute_change` is supplied.
- `missing_samples` — only when `thresholds.expected_interval_minutes` is
  supplied, and the gap exceeds twice that interval.
- `stale_sensor` — only when `thresholds.stale_after_minutes` is supplied
  *and* the caller passes an `as_of` reference time (the API always does,
  using the request's own server time).
- `bad_quality` — whenever a reading's stored `quality` flag is present and
  not `"good"`.
- `relative_increase` / `relative_decrease` — **always evaluated, with no
  threshold required**: if the latest value in the window exceeds (or falls
  below) every preceding value, this reports exactly
  `"Latest value increased relative to preceding values in the window."` —
  the deterministic interpretation the spec asks for, and nothing stronger.

None of these ever names a failure mode. A dedicated test
(`test_no_observation_ever_names_a_diagnosis`) asserts that no observation
string contains "bearing", "failure", "damage", "cavitation", "diagnos", or
"impeller".

## API

Ingestion (existing FastAPI/Pydantic conventions: `extra="forbid"`,
`IngestionConflict` → `409`, `ValueError` → `422`, dependency failure →
`503`):

```text
POST /data/maintenance/ingest   {source_path, facility_id?, synthetic}
POST /data/sensors/ingest       {source_path, facility_id?, synthetic}
```

Read-only queries (no request ever needs write access to plant state; these
are advisory read paths only):

```text
GET  /maintenance/history?equipment_tag=&work_order_id=&maintenance_type=&status=&start=&end=&limit=
GET  /maintenance/work-orders/{work_order_id}
GET  /sensors/readings?equipment_tag=&sensor_tag=&measurement=&start=&end=&limit=
GET  /sensors/latest?equipment_tag=&sensor_tag=
POST /sensors/features           {equipment_tag, sensor_tag, start, end, rolling_window?, thresholds?}
```

Every maintenance/sensor result carries a `citation` (`source_filename`,
`source_sha256`, `source_row_number`) so a future agent can cite
`"maintenance_history.csv row 14"` directly from stored provenance rather
than a generated string. `POST /sensors/features` additionally returns a
`citation_label` (e.g. `"pump_p204_sensor_data.csv 2026-09-16T10:00:00Z to
10:30:00Z"`) and a `provenance` list covering every reading that contributed
to the computed features.

## Configuration

Root `.env` / environment settings:

| Variable | Default | Meaning |
| --- | --- | --- |
| STRUCTURED_CSV_MAX_BYTES | 10485760 (10 MiB) | Maximum accepted CSV size |
| STRUCTURED_CSV_MAX_ROWS | 50000 | Maximum accepted data rows per CSV |
| STRUCTURED_QUERY_MAX_LIMIT | 2000 | Hard clamp on every query `limit` |

There is deliberately no configured default for anomaly thresholds
(`maximum`, `minimum`, `max_absolute_change`, `expected_interval_minutes`,
`stale_after_minutes`) — every one of them is opt-in and request-supplied
only, so behavior never depends on a hidden default the caller didn't ask
for.

## Artifacts

```text
data/processed/maintenance/normalized/<structured_data_source_id>.json
data/processed/sensors/normalized/<structured_data_source_id>.json
data/processed/sensors/features/<generated_id>.json   (one per POST /sensors/features call)
```

`data/processed/sensors/windows/` remains unused in this phase — reserved,
not repurposed.

## Limitations

- **Prototype scale, not a production CMMS/historian.** `sensor_latest` and
  `sensor_features` fetch the full matching row set for the requested
  equipment/window into memory rather than using a windowed/paginated query;
  this is appropriate for the small synthetic datasets this phase targets and
  is a known scaling limit for a real historian-sized deployment.
- **No stored per-asset thresholds.** Anomaly thresholds are request-supplied
  only; a "configured limits per equipment/sensor" table is future work
  (explicitly allowed by the spec but not built here, to avoid over-scoping
  Phase 3C).
- **No unit conversion.** Units are stored and returned verbatim; comparing
  or aggregating across differing units for the same sensor_tag is not
  attempted.
- **Auto-created equipment rows are unlabeled.** An equipment tag seen for
  the first time in a maintenance/sensor CSV gets `equipment_type="unknown"`;
  a real name/type/location must come from a document or a future equipment
  master import.
- **No topology, no diagnosis, no plant-state write.** This phase does not
  and must not infer causality, connectivity, or equipment condition from
  sensor/maintenance data — that is explicitly deferred to a future
  agent/reasoning layer with human approval.
