# Phase 4E — Maintenance & asset reliability agent

Replaces the 4B stub for `maintenance`. Output schemas: **S4** (general
maintenance assessment), **S6** (sensor-window interpretation via the
threshold loop), **S5** (refusal — per D-004's inclusion of S5 in this
sub-phase's schema set even though the continuation doc's own per-sub-phase
header omits it).

Written as part of the unsupervised autonomous run described in
`docs/phase4-autonomous-continuation.md`; see `docs/phase4-decisions.md`
D-013/D-014 for this sub-phase's non-obvious choices.

## New modules

```
app/agents/observation_language.py   asymmetric failure-mode word ban (observations only)
app/agents/prompts/maintenance.py    two system prompts (S4 general, S6 threshold-loop)
app/agents/nodes/maintenance.py      the maintenance agent itself (both schemas)
```

Modified (additive): `app/agents/enforcement.py` (new
`enforce_citations_and_diagnostic_language`), `app/agents/graph.py` (routes
`maintenance` to `maintenance_node`).

## The safety property: the model never performs arithmetic or asserts a threshold; observations never name a failure mode

### The threshold loop (S6 path)

```
retrieve_documents(query)                                    -- SOP evidence
    -> _extract_threshold(sop_refs)                           -- Python regex, not the model
       finds the first SOP chunk whose quoted text matches
       "maximum/max/limit/threshold/(shall) not exceed" + a
       numeral within 15 characters
    -> (sop_ref, threshold_value) or (None, None)
if found, and get_latest_reading() names a sensor_tag for this asset:
    compute_sensor_features(thresholds.maximum=threshold_value)  -- Phase 3C
       (app/agents/tools/sensors.py, built in 4B; the actual comparison
        happens inside app.services.sensor_features.detect_anomalies,
        pure Python, already tested against the diagnosis-word ban in
        Phase 3C's own test_no_observation_ever_names_a_diagnosis)
    -> SensorInterpretation, with observations/anomaly_status/citations/
       asset_tag/time_window ALL deterministically overwritten
       (_threshold_loop's model_copy(update={...})) regardless of what the
       model returned for those fields -- see D-013. Only `hypotheses`,
       `required_checks`, and `confidence` are taken from the model.
```

A threshold is structurally impossible to use without its SOP citation: the
regex only ever returns `(ref, value)` together, from the same matched
quote, never a bare number. If no SOP chunk yields a numeral, or no sensor
reading exists for the asset, the loop is never entered at all — the node
falls straight to the S4 path with whatever evidence was already gathered.
If the loop runs but nothing actually crosses the cited threshold (an empty
`observations` list from Phase 3C), the node falls back to S4 as well,
rather than emitting an empty S6 — the sensor evidence gathered is still
real evidence, just not an anomaly finding.

`anomaly_status` is computed deterministically too
(`_anomaly_status`), mapping the deterministic observation `kind` values
Phase 3C's `detect_anomalies` already emits
(`threshold_exceeded`/`threshold_below` → `critical`;
`sudden_change`/`missing_samples`/`stale_sensor`/`bad_quality`/
`relative_increase`/`relative_decrease` → `warning`; none → `normal`) —
never left for the model to assess, for the same reason as the observations
themselves (D-013).

### The asymmetric observation/hypothesis validator (S4 path)

`app/agents/observation_language.py` reuses Phase 3C's own forbidden-word
list verbatim (`"bearing"`, `"failure"`, `"damage"`, `"cavitation"`,
`"diagnos"`, `"impeller"` — pinned in `backend/tests/test_structured.py` as
`FORBIDDEN_WORDS`, generalized here rather than re-derived) and applies it
**asymmetrically**: `enforce_citations_and_diagnostic_language()`
(`app/agents/enforcement.py`) checks the model's free-text `observations`
against this list, in the same bounded reject-or-regenerate shape as 4C's
citation enforcement and 4D's authorisation-language enforcement — one
regeneration attempt, then a structural refusal, never a silently-stripped
violation. `hypotheses` are never checked against this list — the schema
itself (built in 4C, `MaintenanceHypothesis`'s `model_validator`) already
requires every hypothesis to carry `supporting_evidence` or
`contradicting_evidence`, which is the correct place for a named failure
mode to live.

The S4 path is used whenever the threshold loop does not apply: gathered
evidence is SOP chunks (`retrieve_documents`), maintenance history rows
(`get_maintenance_history`), and — only when the threshold loop was never
entered — the latest sensor reading (`get_latest_reading`). All three
appear as delimited, labelled evidence blocks (reusing
`app/agents/prompts/shared.py::format_evidence_block`), structured-data
rows rendered as `json.dumps` of the row dict (mirroring 4D's
`_row_block` pattern) since a `csv_row`/`sensor_window` `EvidenceRef`
carries no `.quote` the way a `document_chunk` does.

## Equipment-tag requirement

Unlike knowledge (which can answer a tag-free question) and safety (which
can still gather SOP/incident evidence for a tag-free emergency), the
maintenance domain is fundamentally asset-scoped: every schema here
(`MaintenanceAssessment.asset_tag`, `SensorInterpretation.asset_tag`)
requires one. A query with no deterministically-detectable equipment tag
(`app.services.sparse.identifiers`, the same extractor D-011 introduced for
4D) refuses immediately with `S5`, before any tool is called.

## Limitations

- The threshold-numeral regex (D-014) is deliberately narrow — a limit
  phrased with more than ~15 characters between the keyword and the number
  (e.g. "the maximum permissible value recorded shall be 10") will not be
  extracted, and the query falls through to the S4 general-assessment path
  instead of the threshold loop. This is a safe degradation (never a false
  threshold), not a crash, but is narrower coverage than a human reading
  the same SOP would achieve.
- `hypotheses[].supporting_evidence`/`contradicting_evidence` entries are
  not validated for evidence_id existence the way top-level `citations` are
  (no `Citation` object backs them in the S4/S6 schemas, just bare
  strings) — unlike 4C/4D/4F's citation enforcement, a hypothesis could in
  principle reference a string that isn't a real evidence_id. Flagged here
  rather than silently assumed correct; a natural follow-up, not required
  by this sub-phase's own safety property (which is about arithmetic and
  observation language, not hypothesis citation integrity).
- Only the first detected equipment tag in a multi-tag query is used
  (`tags[0]`) — consistent with 4D's `_MAX_COMBINED_TAGS` bounding
  philosophy (D-011), but a query naming two assets together will only be
  assessed for the first.
- The threshold loop's lookback window (`_THRESHOLD_WINDOW_DAYS = 7`) is a
  fixed constant, not derived from the query text, which carries no
  explicit time range of its own — see D-014.
