# Phase 10.2 — Qwen/Ollama turn-confusion runtime probe

Verdict: **PHASE 10.2 PROBE COMPLETE**

Primary recommendation: **B. GENERIC HARNESS FIX**. In the measured cases, submit the final-answer request as a fresh system/user conversation containing the original request/context, actual returned evidence, reference catalog and final schema. Keep planning separate and retain its output for tool dispatch and scoring. Do not include the preceding planning task/schema/assistant response in the answer conversation. This recommendation is not applied globally by this probe.

## Recovered state and controls

HEAD is `1fc238e Phase 10.1: diagnose benchmark interface and model failures`. Contrary to the handoff's uncommitted-state description, Phase 10.1 harness, tests, diagnostics and results are committed and present. They were preserved. All tracked benchmark files were compared byte-for-byte with HEAD after the probe; all match. Unrelated frontend, manifest, Phase 9 and local tooling files were untouched. Initial and final diff checks pass with existing Windows line-ending warnings only.

Only JSON-003 and OBS-005 were used. Four new model calls, no planning calls, retries, validation/blind runs, downloads or changes to benchmark truth, validators, production code or runtime configuration. The Phase 10.1 saved planning output and actual tool results were replayed rather than regenerated. Both saved plans are clarification plus asset_registry_lookup; both returned the assigned registry evidence, REG-U2-001. No missing P&ID evidence was newly supplied to improve results.

The JSON companion stores the exact messages, wire payloads, native responses, parsed output, schema errors, timings, tokens, recorded plans/evidence and isolated temporary helper source. Expected answers/routes/tools/scoring values were not added to messages. Assertions verify Mode A exactly reproduces the saved answer messages and A/B have identical non-message request fields, evidence, reference catalog and final S3 schema.

## Runtime

- Ollama 0.34.2; installed qwen3.5:9b, Q4_K_M, 9.7B model details.
- Modelfile: `TEMPLATE {{ .Prompt }}`, `RENDERER qwen3.5`, `PARSER qwen3.5`. No replacement template was installed.
- Endpoint: local `POST http://127.0.0.1:11434/api/chat`, stream=false, think=false.
- Options: temperature=0, seed=42, num_ctx=16384, num_predict=1536; inherited model parameters include presence_penalty=1.5, top_k=20, top_p=0.95.
- The current harness uses generate_text: schema instructions appear in message content; no native `format` or `tools` parameter is sent. Both probe modes preserve that behavior. No implicit repair calls or transport retries.
- Timeout: 900 seconds; all four requests finished within the deadline without runtime errors or truncation.

## Modes and results

A CURRENT: exact saved system/user/assistant/user answer request, including planning schema and saved assistant plan. One answer call per case, not a fresh planning run.

B SINGLE FINAL TURN: system/user only. Same system text, original request/context, returned evidence, reference catalog, final schema and final task. Planning instructions/schema and assistant plan removed.

C CLEAN NATIVE CHAT: not needed and not run. A and B already use native /api/chat through the existing gateway, with captured native response bodies. Their controlled comparison resolves the requested structural question without two more calls.

| Case | Mode | Schema | Planning-shaped JSON | Seconds | Input / output tokens |
|---|---|---|---|---:|---:|
| JSON-003 | A | INVALID | Yes | 61.919 | 2136 / 26 |
| JSON-003 | B | VALID S3 | No | 65.653 | 1635 / 174 |
| OBS-005 | A | INVALID | Yes | 18.650 | 2143 / 26 |
| OBS-005 | B | VALID S3 | No | 76.170 | 1642 / 192 |

Both A responses were `{"route":"knowledge","tools":["none"]}`. This repeats the planning task/shape, not the exact saved plan values. Both B responses contain tags/warnings, cite REG-U2-001, keep XV-2040 unverified, and leave normalized_tag and equipment_type null. Full raw responses are in the JSON companion. Neither B response has an automated critical finding; this is not a semantic correctness certification. For example, the two B confidence values differ (0.0 and 0.54).

## Interpretation and limits

**TURN CONFUSION REPRODUCED:** 2/2 current-mode answer requests returned a plan instead of the final schema. **HARNESS/PARSER FAILURE NOT OBSERVED:** native response content already has the wrong shape; the unchanged strict parser correctly rejects it. **NORMAL MODEL JUDGMENT FAILURE IS SEPARATE:** saved planning selected incomplete tools and remains outside this answer-turn probe; schema-valid answers do not erase those benchmark failures or establish semantic correctness.

The measured contributing cause is the retained planning conversation/task/contract competing with the final-answer contract: removing that history eliminated the structural failure in both cases, with runtime and evidence unchanged. This experiment cannot separate the influence of prior assistant content from the prior planning instructions/schema because they were removed together. The prompt contains competing structured-output schemas in A; B removes the obsolete one. Native constrained decoding was not used or tested, so no native `format` interaction is established.

There is no controlled evidence that a renderer/parser bug or quantization is the cause: neither was varied. No template or Ollama configuration change is justified. One observation per case/mode supports the narrow generic request-construction recommendation, not a reliability claim across the benchmark. No additional sampling was performed to seek desired results.

## Host-sleep control

The helper requested Windows ES_CONTINUOUS | ES_SYSTEM_REQUIRED on its calling thread for the probe, then cleared it in finally. No system-wide power setting changed. Wall-clock elapsed time minus Windows QueryUnbiasedInterruptTime elapsed time was effectively zero for all four calls (absolute difference below one microsecond); no measurement shows suspend time. The System event query for the probe interval returned NoMatchingEventsFound. This is recorded verbatim in JSON. All four measurements are valid; no sleep interval was subtracted or hidden.

## Files and next action

Created only `benchmark/reports/phase10_2_runtime_probe.md` and `.json` in the repository. The isolated helper ran from the OS temporary directory; its source is archived inside the JSON for reproducibility. The normal inference budget was four of six calls, with zero diagnostic retries.

Recommend the fresh final-answer conversation as a future generic harness change, with its own focused contract tests and authorized evaluation. Do not replace the model or renderer, weaken validation, reinterpret existing benchmark failures, or begin Advanced-A as part of this probe. No commit was made.
