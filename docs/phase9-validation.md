# Phase 9 validation

## Implementation and scope

The starting point was Phase 8 commit `f9fbefa`, with only `.codex/` and
`claudex-loop/` untracked. Neither directory was modified or staged.

The existing pipeline is retained. The combined Safety/Maintenance node now
computes a bounded recorded sensor window through the existing read-only feature
tool, deriving its threshold from retrieved SOP evidence. Historical timestamps
remain historical. S7 adds separate observations, hypotheses and limitations;
the generation schema explicitly requires evidence fields and nonempty citations.
The existing citation, observation-language, authorization, governance, evidence
integrity, approval and audit boundaries remain active.

Live validation identified and repaired a pre-existing prompt/validator mismatch:
Safety, Maintenance and Optimization prompt builders gave CSV evidence descriptive
locators instead of the exact source-row locator required by the citation validator.
They now supply the evidence reference's locator. No citation check was relaxed.
Observation repair errors are distinguished from authorization errors.

Tool names, durations and evidence IDs are retained in the existing graph-step
timings JSON; there is no new trace table or endpoint. No tool arguments, tokens
or credentials were added to those trace records.

The frontend retains Phase 8 pages, shows an explicit as-drawn/OCR limitation,
and allows a bounded 2,100-second query wait to cover the demo's process-only
2,000-second agent budget. It still does not automatically retry submissions.

## Source data and import

`scripts.seed_phase9` uses the ordinary PDF, CSV and real OCR ingestion handlers.
It materializes the existing fictional source inventory and Phase 3C P-204
measurements/history, explicitly mapping family records to P-204A. It does not
read benchmark cases, expected answers or scoring notes. Evaluation assets remain
unchanged. Source provenance is recorded in `data/manifests/dataset_licenses.md`.

Observed import/re-import:

- SOP-P204-001-demo-v1.pdf: one indexed chunk; repeat status duplicate.
- MH-P204-demo-v1.csv: three rows; repeat status duplicate.
- SENSOR-P204-A-demo-v1.csv: five rows; repeat status duplicate.
- PID-U2-017-R3-demo-v1.png: one page, eight real OCR detections, five regions;
  repeat processing status duplicate; OCR indexed into the existing Qdrant collection.
- Two dedicated local demo accounts created through the existing User/password
  mechanism; existing accounts with differing credentials/roles are not overwritten.

The generated drawing is a labelled synthetic label excerpt, not an actual
engineering connectivity drawing. OCR output stays unverified/ambiguous. The
sensor timestamps are 2026-09-16 10:00–10:20 UTC, not current telemetry.

## Exact live query

> Pump P-204A vibration is elevated. Review the available sensor data, maintenance history, SOP and P&ID evidence and advise what should be done.

Expected route is the existing `combined_safety_maintenance`: a Safety handler
with Maintenance structured-data tools and Knowledge retrieval, not three new
agents or a parallel demo pipeline. Optimization is not appropriate for this
abnormal-condition triage query.

## Earlier live attempts retained

- Initial client wait expired at 660 seconds. A subsequent database check showed
  the combined graph run completed in 843.8 seconds without a governed draft.
  The client did not capture its final response. This exposed the client/backend
  timeout mismatch; it is not counted as a successful advisory.
- Captured retry: correct route and evidence, but S5 `insufficient_evidence`
  because the model emitted no citations after bounded regeneration. The
  generation contract was tightened; citation enforcement remained unchanged.
- Next captured run: S5, with three CSV locator mismatches and a language
  validation failure. This led to the source-locator correction described above.

Reports/logs remain local and Git-ignored:
`data/processed/phase9-live.json`, `phase9-live-retry.json`,
`phase9-live-final.json`, and repository-root `phase9-*.log`.

## Validation method and limitations

`scripts.validate_phase9` calls the actual running FastAPI HTTP application with
real requester/reviewer sessions and `qwen3.5:9b` through Ollama. Its two independent
queries are intended to validate approve/release/revoke and reject/blocked-release
on actual model-generated drafts. It stops on a refusal; it never substitutes a
mocked or hardcoded recommendation. It records trace, evidence, citations,
governance responses, audit verification and sovereignty proof.

The focused unittest checks use controlled model results for reproducible
structural/safety assertions. They are not claimed as live inference. Citation
identity/locator validation and lexical diagnostic guards are not a general
semantic-entailment proof; qualified reviewers must assess the advisory's content.

PostgreSQL and Qdrant were started/checked through the existing Compose file.
Ollama reported `qwen3.5:9b`; FastAPI health/readiness/proof and agents returned
HTTP 200. The Vite frontend served HTTP 200. Browser automation reported no
available browsers (Chrome and in-app browser both unavailable), including a
fresh check after resuming. No interactive browser/screenshot walkthrough is
claimed. Frontend rendering, HTTP transport and build checks are separate evidence.

## Test commands

From `backend`, with `PYTHONPATH=tests` and `WORKBENCH_TEST_POSTGRES=1`:

```powershell
.\.venv\Scripts\python.exe -m unittest test_phase9 test_phase7 test_phase5f_security -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

From `frontend`:

```powershell
node --test src/services/api.test.js src/WorkspacePages.test.js
npm run lint
npm run build
```

From repository root: `git diff --check`.

Latest automated results after the sensor-citation and hypothesis corrections:

| Check | Result |
| --- | --- |
| Phase 9 targeted | 20 passed (included in the 68-test Safety/Maintenance targeted run) |
| Phase 7 + Phase 5F security | Passed in targeted run and final full suite, including enabled PostgreSQL checks |
| Full backend (`WORKBENCH_TEST_POSTGRES=1`) | 553 run: 552 passed, 1 skipped; process exit 0 |
| Phase 8 frontend API/rendering checks | 7 passed |
| `npm run lint` | PASS |
| `npm run build` | PASS, 33 modules |
| `git diff --check` | PASS; Windows LF/CRLF notices only |

The skipped backend test is the opt-in live foundation query; the Phase 9 HTTP
validator exercises actual inference independently. Targeted tests overlap the
full suite and are not additional unique tests. The full-suite log is
`phase9-full-final.log`; final frontend build/test results were captured in
the session tool output. These checks do not alone establish a successful demo.

Vite/Node subprocess checks required approved execution outside the Windows
sandbox after EPERM. No dependency was added or security setting relaxed.

## Resumed live validation

The locator-corrected attempt (`data/processed/phase9-live-locators.json`)
returned HTTP 504, `Model gateway timed out`. No successful advisory or approval
cycle is claimed for that attempt. Its independent audit snapshot verified 14
events; sovereignty still reported local Qwen, PostgreSQL and Qdrant, zero
external AI dispatches, and no firewall attestation.

A subsequent retry uses a process-only `MODEL_TIMEOUT_SECONDS=900` override;
the root `.env` is unchanged. Ollama reported 74% CPU / 26% GPU placement and
approximately 2.8 generated tokens/second. Readiness does not guarantee timely
inference on this hardware.

Live health, readiness, sovereignty, agent status and an out-of-domain refusal
were captured in `data/processed/phase9-live-ui.json`. The actual refusal and
status data rendered through the existing React components; the HTML is in
`data/processed/phase9-live-ui.html`. This is server rendering, not an interactive
browser walkthrough. Browser inventory remained empty on the resumed attempt.

The 900-second model retry (`phase9-live-resume.json`) completed its first
generation, entered the existing validation repair, then exhausted the overall
1,100-second agent deadline and returned HTTP 504. The next attempt
(`phase9-live-bounded.json`) uses a 2,000-second overall budget and a 2,100-second
client wait, with the same 900-second model timeout and the same repair count.
The prompt now requests concise text fields; enforcement logs only counts of
citation, authorization and observation failures, never draft text. The 43
focused Phase 9 and Safety tests passed after these changes.

### First accepted live advisory

The bounded run produced S7 on route `combined_safety_maintenance`, request
`fe7d058c-bf7b-4a09-9a24-05d68c0f8a8b`, run
`3bc236f9-08d2-4bb7-9b66-c7e9cfd488a5`, revision
`020702d4-9839-58ac-b5aa-b5eea27246e7`. Citation and observation checks passed;
one authorization-language match triggered the existing repair, after which the
response passed. Evidence binding was VERIFIED and the revision was PENDING_REVIEW.

Observed content included 8.2 mm/s versus the cited 7.1 mm/s alert threshold;
the SOP citation separately retained the 11.0 mm/s high-high threshold. Strainer
fouling and bearing wear appeared as hypotheses, with historical/synthetic limits
and an explicit statement that threshold crossing does not prove a cause.
The advisory proposed procedure review and sensor verification. Qualified review
remains necessary: hypotheses and confidence values are model interpretations,
not confirmed diagnoses or calibrated probabilities.

Actual tools were `retrieve_documents`, `get_pid_regions`,
`get_maintenance_history`, `get_latest_reading`, and `compute_sensor_features`.
Key citations were SOP `document_chunk_5735cd346ed28fed` (page 1), maintenance
`csv_row_76c182b86a3b90e8` (row 4), and sensor window
`sensor_window_ee4024a3f3bd1372`. PID-U2-017 R3 regions were supporting OCR evidence
only. Retrieval also returned older synthetic drawing regions; their presence
does not establish relevance, topology or field state.

The real reviewer approved this revision; advisory release returned HTTP 200 and
RELEASED. Revocation returned REVOKED, and the next release returned HTTP 403.
No equipment command exists in this workflow. The actual response and decision
results rendered through React to `data/processed/phase9-live-advisory.html`,
including observations, hypotheses, limitations and the as-drawn notice.

### Second draft exposed additional validation gaps

The separate request `4bc5d357-5568-4761-bc31-010ebb864c0c` created revision
`f4c0a319-a865-56d7-a01b-b941804aa33f`, but the live validator failed because
sensor claims lacked a sensor citation. One hypothesis also used unqualified
"is causing" wording. This is not counted as a successful grounded demo response.
The actual reviewer subsequently rejected that revision with those reasons;
release returned HTTP 403 and the chain verified. The record is preserved in
`data/processed/phase9-live-rejection.json`.

The combined agent now requires citations for all computed sensor-window evidence
inside the existing bounded citation repair. The shared hypothesis schema rejects
unqualified causal constructions such as "is causing"; this is an additional
language heuristic, not a general semantic-entailment proof. The prompt explicitly
requests tentative causal wording and exact sensor-window citations. Two focused
regressions cover the observed failures; 68 Phase 9/Safety/Maintenance checks passed.

## Final live result: PASS

`data/processed/phase9-live-grounded.json` records `passed: true` on the final
implementation. The validator exited 0. Both independent HTTP queries used the
exact primary query, real retrieval and local `qwen3.5:9b`; neither needed a
generation repair. Both returned S7, `combined_safety_maintenance`, verified
evidence binding, and PENDING_REVIEW with human approval required.

| Check | Observed result |
| --- | --- |
| Approve query | Request `6e102420-fb69-4f05-9a42-ac6354e671b8`; run `be8f2346-2548-4342-a591-9b8bdd399a9f`; 487.6 seconds |
| Approved revision | `5e9ef497-8061-5a9d-b7fd-966ad4d50ca3`; release 200 / RELEASED; revoke REVOKED; subsequent release 403 |
| Reject query | Request `edf8d84b-961d-4d20-bf8a-0ea785038aa9`; run `31f9e8ee-8acf-4ec7-ab19-067d4ff9aa08`; 409.4 seconds |
| Rejected revision | `5f0e4bda-10b8-5c5b-ba5c-96be1163974d`; REJECTED; release 403 |
| Audit | Required creation, approval, release, revocation and rejection events matched to their revision IDs; chain VALID, 46 events at verification |
| Sovereignty | Ollama / qwen3.5:9b; PostgreSQL, Qdrant and data paths local; hosted/cloud AI false; 4 local inference dispatches, 0 external dispatches |

Final observations report 8.2 mm/s against the 7.1 mm/s alert threshold and
5.1 mm/s absolute change. SOP, maintenance and sensor-window citations are
present with exact source locators. Hypotheses use "may" and "could" for
strainer fouling and prior bearing wear; historical/synthetic limitations are
explicit. Proposals concern procedure review and sensor verification, not
execution. PID regions remain supporting as-drawn evidence only.

The actual final responses, decisions, audit events and proof rendered through
the existing React components to `data/processed/phase9-live-grounded.html`.
The frontend served HTTP 200. No interactive browser walkthrough is claimed:
browser/app inventory remained empty even after the environment update.

Final automated totals: 20 Phase 9 tests; 553 full backend tests run, 552 passed
and one opt-in live foundation test skipped; 7 frontend tests passed; lint,
production build and Git whitespace checks passed. The full suite includes
Phase 7 sovereignty and Phase 5F security with PostgreSQL checks enabled.

No known functional BLOCKER/HIGH remains within the exercised Phase 9 workflow.
Presentation limitations remain: this host took approximately 6.8–8.1 minutes
per query, interactive browser verification must be completed manually, and
retrieval includes some older synthetic OCR regions. Do not claim low latency,
semantic-proof-level diagnosis validation, or firewall isolation. Rehearse on
the actual presentation hardware. The API validator signs out both accounts;
FastAPI, Vite, Ollama and the existing data services are left available locally.

Verdict: **PHASE 9 COMPLETE**, with the validation scope and limitations above.
No commit was created and Phase 10 was not started.
