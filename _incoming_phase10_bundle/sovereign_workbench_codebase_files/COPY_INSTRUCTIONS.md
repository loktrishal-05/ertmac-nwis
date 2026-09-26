# Files to copy into sovereign-agentic-workbench

Extract this ZIP into a temporary folder. Copy/merge its `benchmark/` directory into the root of your existing `sovereign-agentic-workbench/` repository. Do not replace or delete the existing benchmark directory as a whole. This is a prepared file bundle, not an applied repository change.

| Destination in repository | What to copy |
|---|---|
| benchmark/cases/ | benchmark_cases_final.jsonl, benchmark_cases_final_readable.md, benchmark_split_manifest.json |
| benchmark/corpus/ | Both synthetic_corpus/ and synthetic_corpus_part2/ directories |
| benchmark/mappings/ | benchmark_corpus_mapping_final.json |
| benchmark/reports/ | Finalization report, static validation results, and preserved source_inputs/ |
| benchmark/harness/evaluate.py | Keep your existing file; none is generated or supplied here |
| benchmark/results/ | Leave empty until evaluation is separately authorized |

The split manifest resolves its benchmark_file relative to benchmark/cases/. The combined corpus mapping resolves paths relative to benchmark/mappings/. Its active inventory selects the two hardened *_final P&ID files. The Part 2 authoritative manifest is corpus_manifest_part2_final.json. The original corpus files and historical reports remain preserved; do not recursively ingest archival copies or report/source metadata as evidence.

All 75 cases and the exact 15/15/45 split are included. There are 24 logical evidence artifacts and 44 active corpus files. This packaging step changed paths in the combined mapping and final Part 2 manifest and refreshed the manifest hash; it did not change case or corpus content bytes. Relocated paths, selectors, file sizes and hashes were verified.

## Remaining issues

BENCHMARK FINALIZATION NEEDS REPAIR remains the verdict. The actual repository/harness was not supplied, so its path conventions, tool registration, model-approval rejection, metadata stripping and final-file loading remain unverified. JSON-004, REF-005 and HITL-003 have no source-assigned bounded sensor window. Inspect existing harness bindings before choosing one; no new fixture was invented.

No model inference, Phase 10 evaluation, Advanced-A/B/C, application edits or commits were performed. This ZIP contains no evaluate.py, no new harness code and no fabricated results. To finish repository integration, supply the existing evaluate.py and the related benchmark loader/configuration files for inspection.
