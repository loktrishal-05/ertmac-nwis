# REF-005 binding resolution

**REF-005 UNRESOLVABLE FROM SOURCE**

**Verdict: REF-005 SOURCE DATA MISSING ? DO NOT INVENT**

Inspected at 2026-09-27T04:16:44.811706+00:00; HEAD `6dba5c11d1cc6e0479413b8c860b4167ca4c25aa`.

## 1. Root cause

This is a pre-existing missing case-to-window assignment, not a conversion omission supported by recoverable source evidence. The source identifies a sensor *family*, but never assigns REF-005 a specific bounded member. Artifact-level ?ready?/?all_required_evidence_resolved? labels establish file/family availability only. They do not establish an executable bounded-window binding.

The frozen loader correctly refuses it: `benchmark/harness/assets.py` requires a non-empty `window_bindings` for `sensor_timeseries_window_family`; `benchmark/harness/evaluate.py:resolve()` raises `Blocked: No source-assigned bounded sensor window.`

## 2. Authority and search scope

No authoritative REF-005 window assignment was located. Searched active cases/mapping/corpus, finalization and static-validation reports, historical original/final case exports, original evidence requirements/decision/conversion documents, original corpus manifest/mapping, incoming packaged and loose source copies, and both original corpus ZIPs (including text/build-script entries). Inspected current harness, its fixture/asset test, integration records, and the original Phase 10 commit. No source build scripts were executed.

The active finalization report designates the final cases, split manifest and combined mapping as authoritative. Historical copies were inspected for provenance, not promoted into new benchmark truth. Only case input/context and source selectors were used to assess assignment; expected answers/scoring were not used to select or reconstruct evidence.

## 3. Exact provenance

1. `benchmark/cases/benchmark_cases_final.jsonl`, record `evaluation_id=REF-005`, split `validation`: input ?Give exact remaining bearing life in hours.? Context ?No prognostic model or validated degradation curve?. Required sources `MH-P204` and `SENSOR-P204-A`; no timestamp or bounded-window identifier. Historical original/final JSONL copies preserve this input/context without an assignment. The older `data/evaluation/model_eval_cases.jsonl` says ?Available history/sensors insufficient?, also without a window.
2. `benchmark/mappings/benchmark_corpus_mapping_final.json`, REF-005 binding: `MH-P204` points to existing maintenance CSV/JSON. `SENSOR-P204-A` points to `index.json` and W1.csv?W12.csv; `window_bindings=[]`, `window_binding_status=family_resolved_specific_window_unspecified`, `contextual_sensor_windows=[]`. Listing all files is an inventory, not authorization to concatenate or select a window.
3. `benchmark/corpus/synthetic_corpus/timeseries/SENSOR-P204-A/index.json` contains 12 explicit windows with start/end timestamps and `referenced_by` assignments. **None names REF-005 or JSON-004.** Its note explains that windows come from different days because they contain deliberately contradictory readings. Equipment identity alone therefore cannot choose one.
4. `benchmark/reports/benchmark_finalization_report.md:111` explicitly states that JSON-004, REF-005 and HITL-003 have no source-specified bounded window; complete families/paths were mapped, and no scenario was chosen. Its section 4 claim of 75/75 evidence resolution is family-level coverage, qualified by that explicit limitation.
5. `benchmark/reports/benchmark_validation_results_final.json:3641` (`unresolved_sensor_bindings`) records all three cases. Exact reason: ?Source case, corpus index and supplied mapping do not select a bounded window. No selection invented.?
6. `_incoming_phase10_bundle/sovereign_workbench_codebase_files/COPY_INSTRUCTIONS.md`, ?Remaining issues?, repeats the same missing-assignment condition. Packaged mapping and loose finalization copies provide no contrary assignment.
7. `docs/phase10.md:24`, `docs/phase10-validation.md:122`, and `benchmark/reports/phase10_asset_integration.json` preserve the three unresolved IDs during repository integration.
8. `benchmark/harness/test_evaluate.py:174` (`test_final_assets_split_coverage_and_selectors`) explicitly expects the unresolved set `{JSON-004, REF-005, HITL-003}`. That assertion is already present at Phase 10 commit `ecb79c9`, before the Phase 10.3 freeze. No separate existing harness assignment was found.

Original ZIP verification: the `SENSOR-P204-A/index.json` bytes inside `synthetic_corpus_part1.zip` are identical to the active file, SHA-256 `98a538425deeecacc9460d144d96bcb71de04556ff5c481161e98a3db804c4ae`. The E-101 index is also byte-identical, SHA-256 `ba89d460a8777ac9dc7fd082a73b4f9331b88dcf918f30ca014cf729c5253f82`. Thus an assignment was not lost by copying these indexes into the repository.

The existing P-204 windows span separate dates September 1?12, 2026; each has explicit endpoints and assignments to other cases. A window that appears thematically similar, shares an asset, or belongs to a neighboring refusal case is not a source assignment. Neither that inference nor expected-answer reasoning was used.

## 4. Repair decision

**CASE B. No repair made.** No source-backed bounded assignment exists in the inspected repository/source package. This is an absence of assignment, not an absence of sensor CSV files.

No window was invented, selected, concatenated, or borrowed from another case. No mapping, corpus, case, manifest, test, validator, scoring code, Stage 2 runner, or readiness report changed. No protected hashes were repinned. This report records the source limitation; it is not a benchmark erratum changing truth.

## 5. Semantics and frozen behavior

Benchmark semantics: **unchanged**. Expected answers and scoring: **unchanged**. Frozen-interface behavior: **unchanged**, including fail-closed resolution of the three known IDs.

All 101 frozen benchmark files remain byte-identical to Phase 10.3 commit `39e6d16`. All 46 authoritative corpus/manifest hashes passed. Case SHA-256 remains:

`8bbb958865e0042a6951c05342b4cb67e4791e0515f32b2831607b408c9176bb`

Counts remain 75 total, 15 DEV, 15 VALIDATION, 45 BLIND, 15 categories.

## 6. DEV + VALIDATION readiness

Zero-inference resolution through the unchanged loader:

| Split | Selected | Resolved | Unresolved |
|---|---:|---:|---|
| DEV | 15 | 15 | None |
| VALIDATION | 15 | 14 | REF-005 |
| Combined | 30 | 29 | REF-005 |

The requested fully executable 30/30 run is **not ready**. Existing Stage 1 orchestration correctly aborts before inference. No Stage 2 results were generated.

## 7. JSON-004 / HITL-003 read-only findings

| Case | Split | Family | Source assignment | Current DEV+VALIDATION impact |
|---|---|---|---|---|
| JSON-004 | BLIND | SENSOR-P204-A | Empty window_bindings; none of W1?W12 references this ID | None; outside current selected split |
| HITL-003 | BLIND | SENSOR-E101 | Empty window_bindings; none of E1?E4 references this ID | None; outside current selected split |

Their absence is explicitly recorded in the same finalization/static-validation sources. No direct conversion omission is proven; neither was repaired. Read-only metadata inspection only: no blind inference or evaluation. These known data issues should be handled consistently in any later authorized blind protocol, rather than discovered after model selection and opportunistically filled.

## 8. Safest deadline-compatible proposal ? not implemented

Predeclare a data-error handling protocol identically for every candidate before any comparison inference:

- Retain all 30 planned case rows and preserve REF-005's original ID, split, expected answer, and scoring definition.
- Record REF-005 as `status=NOT_RUN`, `error_type=DATA_BINDING_ERROR`, with the frozen loader's exact error and **zero model calls**. It is neither a model PASS nor a model FAIL and cannot be treated as a successful refusal.
- Execute only the other 29 source-resolvable cases under the unchanged model-facing interface and validators. Do not synthesize even a partial evidence prompt for REF-005.
- Publish explicit coverage: DEV 15/15, VALIDATION 14/15, combined 29/30. Compare candidates on the same 29-case subset, with denominators and the missing category observation disclosed; do not claim a completed 30-case evaluation or hide the case from output.
- Preserve existing failure/semantic-review rules for executed cases. A data exception must not improve reported model performance by being counted as a pass.
- Keep all 45 BLIND cases gated. Before any later authorized blind execution, predeclare the same treatment for the two already-known missing bindings; no blind results or fixtures are created now.

This is a **proposed execution-accounting exception**, not a binding repair. It requires explicit authorization to change the Stage 2 orchestration/protocol; the current stop-on-unresolved preflight remains intact. The alternative is an authoritative source-owner assignment and a transparent versioned benchmark correction, which would create new source truth rather than recover a proven omission. No arbitrary choice is justified by today's deadline.

## 9. Validation and changes

- Zero-inference binding resolution: 29/30; REF-005 blocked as documented.
- Both known blind bindings inspected read-only, not evaluated.
- Frozen comparison: 101/101 byte-identical; corpus/manifest hashes: 46/46 match.
- Existing harness suite: **26 tests passed in 0.102 seconds**, controlled fixtures only, no model inference.
- `git diff --check`: passed before and after report creation.
- Only file created by this task: `benchmark/reports/ref005_binding_resolution.md`.
- All prior modified/untracked files, including Stage 1 reports, remain preserved. No commit, database action, model request, Stage 2 run or BLIND run.

## 10. Exact Git status

```text
 M .codex/hooks.json
?? .codex/test_hooks.py
?? .impeccable/
?? benchmark/reports/final_model_runtime_readiness.json
?? benchmark/reports/final_model_runtime_readiness.md
?? benchmark/reports/ref005_binding_resolution.md
?? claudex-loop/
?? docs/tooling-health.md
```

**REF-005 SOURCE DATA MISSING ? DO NOT INVENT**

STOP.
