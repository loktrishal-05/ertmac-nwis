# B2 maintenance / sensor intelligence

B2 adds deterministic, read-only analysis at `POST /sensors/intelligence` and
the registered `analyze_sensor_maintenance` tool. It extends the existing
structured sensor and maintenance queries, sensor feature computation, evidence
references, citation validator, and evidence-sufficiency service. Tool calls
use the existing registry and execution observability. No model call or new
model gateway, maintenance persistence, approval, or control subsystem is added.

## API

The existing authenticated sensor router permits `requester`, `reviewer`, and
`admin`. Anonymous requests receive 401; unsupported roles receive 403.
Malformed requests receive 422; database/query failures receive a sanitized 503.
No matching data is a successful response with `INSUFFICIENT` coverage.

```json
{
  "equipment_tag": "P-204",
  "start": "2026-01-10T00:00:00Z",
  "end": "2026-01-10T12:00:00Z",
  "rolling_window": 3,
  "thresholds": {
    "VIB": {"maximum": 4.0},
    "TEMP": {"maximum": 50.0}
  },
  "maintenance_lookback_days": 30
}
```

These are synthetic example thresholds, not operating limits. Real limits must
be supplied by the caller and checked against the authoritative reviewed SOP.
Omitting `thresholds`, or supplying an empty object for a channel, performs no
minimum/maximum comparison for that channel. Limits must be finite and minimum
must not exceed maximum. The tool uses the same request contract as the API.

Both endpoints require start and end, with end strictly after start. Naive
timestamps are interpreted as UTC; offset timestamps are normalized to UTC.
The sensor span may not exceed `AGENT_TOOL_MAX_WINDOW_DAYS` (default 90 days).
Maintenance lookback is 1–365 days before sensor start (default 30), ending at
sensor end. Queries retain the existing inclusive timestamp bounds and
`STRUCTURED_QUERY_MAX_LIMIT` (default 2,000) per dataset. Reaching the cap marks
coverage as possibly truncated, even when exactly that many rows exist.
More than 16 matched channels withholds sensor analysis and requests a narrower
window, bounding pairwise correlation work.

The response includes channel summaries, correlations, maintenance links,
observations, tentative hypotheses, contradicting evidence, recommended checks,
coverage state, warnings, citations, and complete `evidence_refs` with source
hashes and row provenance. `human_approval_required` is always true.

## Calculations and interpretation

- Per-channel min/max/mean and the existing median, standard deviation, net
  change, sample-index slope, and optional rolling means.
- Rate of change is endpoint delta divided by actual elapsed hours. It is
  absent for a single reading or zero elapsed time; it is not an instantaneous
  derivative. The inherited `features.slope` remains per sample, not per hour.
- Threshold crossings count entries strictly above a supplied maximum or
  below a supplied minimum. Equality is within bounds. An initially out-of-range
  sample is an excursion, not an invented crossing from an unseen prior sample.
- Excursions carry consecutive recorded sample counts, extreme value, and the
  time between first and last recorded out-of-range samples. One sample has
  zero observed duration. No continuity between samples is asserted.
- A sustained rise means a trailing sequence of at least three strictly
  increasing readings. A transient spike followed by recovery is not a
  sustained rise and generates no progressive-condition hypothesis.
- Pearson correlation uses exactly matching timestamps with at least two
  aligned samples. No interpolation or lag search occurs. Constant channels
  return no coefficient with a zero-variance explanation.
- Maintenance links compare dated records with the earliest observed change
  onset per channel. They distinguish before, after, and coincident timestamps.
  The physical onset may precede the window; observed onset time is not a claim
  about when the physical condition actually began. Undated history is excluded
  by the existing bounded maintenance query.
- Constant channels inside supplied bounds may provide contrary context for
  equipment-wide interpretations only when at least two timestamps align with
  the changing channel. This does not disprove a localized condition.

## Evidence and safety rules

Observations report measured facts separately from hypotheses. Cross-channel
and temporal observations cite both source windows/events. A trailing rise can
produce an explicitly unverified sensor-variation/equipment-condition hypothesis;
correlation alone cannot. The inherited hypothesis `confidence` field is zero,
meaning unassessed here, not a calibrated probability. Maintenance history is
neither supporting nor contradicting evidence for those condition hypotheses.
Temporal proximity never proves causation, recurrence, or repair effectiveness.

The existing `evidence_sufficiency.source_valid` and `assess` functions check
available source references and citations. B2 combines their result with
deterministic coverage checks and takes the more restrictive state:

- `INSUFFICIENT`: no usable sensor data, any analyzed channel has fewer than two
  readings, or the shared assessor cannot establish required sensor evidence.
- `PARTIAL`: analyzable sensor data with missing maintenance, missing channel
  coverage, missing supplied bounds, inadequate alignment, excluded channels,
  detected sampling gaps, possibly truncated reads, or evidence/citation issues.
- `SUFFICIENT`: those coverage checks pass and the shared assessor agrees.
  This is evidence coverage only, never diagnosis, confidence, SOP validation,
  authorization, or permission to execute.

Channels containing nonfinite readings, explicit non-good quality, mixed units
or measurements, or duplicate timestamps are excluded as a whole with warnings.
Missing quality does not assert a good quality flag. If a supplied expected
interval is exceeded by more than twice that interval, coverage is downgraded;
recorded-duration calculations still do not imply continuous persistence.

Recommendations request qualified human verification, independent measurements,
reviewed SOP bounds, and dated maintenance history. The existing observation and
authorization language heuristics check generated prose, treating channel names,
units, and work-order identifiers as source metadata. These heuristics are not
an authorization boundary. This endpoint creates no work order, action revision,
approval, plant command, or automatic intervention. Existing governance/HITL
remains necessary for any downstream action; a response is not a released advisory.

## Limitations

Analysis is bounded to available database rows. Evidence verification reuses the
repository's source-resolution semantics; it is not an independent calibration
or authenticity audit. Caller thresholds are not independently verified against
an SOP by this endpoint. Missing thresholds and history stay missing.

Only minimum/maximum bounds and expected sampling interval are used from the
shared threshold schema; sudden-change and staleness analysis remain available
through `/sensors/features`. There is no unit conversion, interpolation,
statistical significance test, causal inference, failure diagnosis, recurrence
prediction, or automatic routing change to the existing maintenance agent.
Two aligned points can yield a coefficient but do not establish a robust
relationship. Sensor quality, sampling density, and operating context require
human review.

## Tests and reproduction

`backend/tests/test_maintenance_sensor_intelligence.py` uses the repository's
existing unittest and in-memory SQLite helper, with real bounded SQL queries.
It covers sustained rise, transient spike, upper/lower crossings, persistence,
stable correlation, constant channels, conflicting indicators, before/after/
coincident maintenance, insufficient windows, missing data/history/thresholds,
observation/hypothesis separation, citations, source verification, safe checks,
RBAC, malformed requests, missing database, bad channel data, sampling gaps,
unaligned channels, query/channel limits, repeatability, and tool/API parity.
No `conftest.py`, private virtualenv, model call, or benchmark fixture was added.
Existing registry tests now expect the eighth explicitly registered read-only tool.

Run from this worktree's `backend` directory in PowerShell:

```powershell
$env:MODEL_NAME = 'b2-test-only' # Required settings value; tests use fakes, no inference.
$python = 'C:\Users\Lohith k\Desktop\sovereign-agentic-workbench\backend\.venv\Scripts\python.exe'
& $python -c "import app; print(app.__file__)"
& $python -m pytest tests/test_maintenance_sensor_intelligence.py -q
& $python -m pytest tests -q --tb=short -ra
git diff --check
```

The import check must point to `sovereign-maintenance-intel/backend/app`.
PostgreSQL integration tests retain their existing opt-in environment gates;
skipped tests do not establish live PostgreSQL or concurrency validation.

### Validation result (2026-09-28)

- B2 targeted: **29 passed**, plus 10 passing subtests.
- Canonical frozen-asset guard checks: **4 passed**, including rejection of
  content mutations, mixed line endings, and other non-checkout changes.
- Sensor/maintenance/security/evidence regression selection: **397 passed,
  22 skipped**, plus 28 passing subtests.
- Final full backend: **699 passed, 0 failed, 0 errors, 46 skipped**, plus
  99 passing subtests. Skips are the existing opt-in PostgreSQL/live-model gates.
- `git diff --check`: passed.

Master was integrated by fast-forward from `9f1ec42` to `656f5d0`, preserving
the uncommitted B2 implementation. The overlapping `test_phase5e.py` changes
merged cleanly and retain both B2's read-only tool allowlist and master's
canonical frozen-asset guard. No merge or B2 commit was created.

The former three CRLF byte-hash failures are resolved by master's canonical
guard: it accepts exact committed bytes or their uniform LF-to-CRLF checkout
conversion, then checks the original pinned hashes against canonical Git bytes.
All five expected SHA-256 values are unchanged. All 198 protected benchmark,
evaluation, specification, and frontend files remained byte-identical to the
pre-integration snapshot. No benchmark artifact or integrity expectation was
modified. Status: **COMPLETE — READY FOR MERGE**.
