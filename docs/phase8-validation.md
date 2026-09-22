# Phase 8 validation

## Recovery-session verification (2026-09-22)

The recovered working tree already contained the full integration: three tracked
frontend modifications (83 insertions, 41 deletions), untracked WorkspacePages.jsx,
useApi.js, six API tests, and both Phase 8 documents. HEAD was 559be61 on master.
The existing implementation passed lint, build, and all six API tests before edits.
The LF/CRLF warning was informational; diff whitespace checks passed.

This session preserved that implementation and corrected four display gaps:
readiness now shows the backend's not_ready status on HTTP 503; S5 refusal and
clarification statuses have a prominent notice; empty agent routes/objects are
explicit; loading another approval revision clears the previous action result
and reviewer comment. No backend or API contract changed.

Current checks:

- `npm run lint`: PASS (the package's lint script).
- `npm run build`: PASS, 33 modules (the package's build script).
- `node --test src/services/api.test.js src/WorkspacePages.test.js`: 7 passed.
  The additional rendering check covers S5 states, pending-review notices,
  revision/evidence rendering, HTML escaping, revoked status, empty objects/lists,
  and loading/401/403 messages. These are controlled rendering inputs, not live
  model responses or an end-to-end approval workflow.
- `git diff --check`: PASS.
- Backend tests: not rerun; no backend files changed.
- Live validation: unavailable this session. No listener was found on port 8000;
  `/health` connection attempts failed both inside and outside the sandbox.
  Health/readiness/proof/agents/query/approval/audit live rendering was therefore
  not rerun. No security setting was relaxed to enable testing.

Vite and Node subprocesses initially encountered sandbox EPERM; approved execution
outside the sandbox passed. No new dependencies were installed.

Verdict: **PHASE 8 COMPLETE** for integration scope; no remaining BLOCKER/HIGH
integration defect identified. Current live-service availability remains an
explicit validation limitation. No commit or Phase 9 work was performed.

## Historical validation recovered with the existing implementation

The sections below predate this recovery session. Their live observations were
not repeated here. The existing backend results log ends with 231 tests run,
OK (skipped=1), consistent with the prior automated report.

## Result

PHASE 8 COMPLETE — frontend/backend integration implemented. No remaining
BLOCKER/HIGH frontend integration issue identified. No backend security changes,
commit, or Phase 9 work. `.codex/` and `claudex-loop/` were preserved.

## Automated checks

| Check | Result |
| --- | --- |
| `npm run lint` | PASS |
| `npm run build` | PASS; Vite production build, 33 modules |
| `node --test src/services/api.test.js` | 6 passed |
| Relevant backend/API/security regressions | 231 run: 230 passed, 1 skipped |
| `git diff --check` | PASS |

Backend command, from `backend` with `PYTHONPATH=tests` and
`WORKBENCH_TEST_POSTGRES=1`:

```powershell
.\.venv\Scripts\python.exe -m unittest test_phase5b test_phase5c test_phase5e test_phase5f_security test_phase6 test_phase7 test_agents test_foundation -q
```

This includes real PostgreSQL Phase 5F tests. The one skip was the opt-in live-model
foundation query test. The browser check below exercised an actual model query.
Detailed local logs remain at repository root as ignored
`phase8-backend-results.log`, `phase8-backend-live.log`, and
`phase8-frontend-live.log`.

Node's test subprocess initially failed with sandbox EPERM; the approved retry
passed all six tests. Production builds used the required esbuild subprocess
permission. No source change was made to bypass sandbox restrictions.

The API tests cover session credentials, exact revision binding, server 403
messages, non-JSON/503 failures, empty responses, the health contract, timeouts,
and absence of automatic POST retries.

## Browser validation against real services

Used the actual Vite frontend at `http://localhost:5173` and FastAPI at
`http://localhost:8000`, real PostgreSQL/Qdrant, and host Ollama `qwen3.5:9b`.
FastAPI used a disposable `test_phase8_*` PostgreSQL schema with copied source
rows and two temporary requester/reviewer users. No production user, source
file, or public-schema record was modified. Temporary services/schema/users were
removed and validation browser tabs closed afterward.

Observed in the browser:

- Dashboard: backend Connected, readiness ready, five implemented routes,
  unavailable inventory/live-activity metrics, actual external-call count.
- Login: requester/reviewer sessions established by the backend; logout worked.
- Query: `Recommend a movie.` returned HTTP 200 with the backend S5 refusal,
  displayed visibly with reason and safe next step.
- Real maintenance query for P-101A routed to maintenance and returned HTTP 200.
  It ultimately returned **S5 insufficient_evidence**, because the local model
  failed citation enforcement after bounded regeneration. Route, reason, warnings,
  and expandable source evidence all rendered correctly. Generation took several
  minutes; this was not a successful grounded-answer-quality demonstration.
- Agents: real implemented/guardrail routes and descriptions rendered.
- Sovereignty: actual model/runtime/locality, zero external dispatches,
  observation window and limitations rendered; network enforcement was No.
- Audit: requester received visible 403 denial. Reviewer saw real event type,
  sequence, timestamp, actor and chain verification VALID with hashes.
- Approval-required presentation: two explicitly labelled test-only drafts were
  created through the existing governance service, independent of the model.
  The UI showed PENDING_REVIEW, DRAFT/human approval required, exact revision,
  request/proposal hashes and manifest status. These fixtures had no evidence and
  were labelled as not model-generated or evidence-backed advice.
- Reviewer controls: approve → APPROVED; view advisory → RELEASED; revoke →
  REVOKED; second draft reject → REJECTED. All were real backend API calls on
  disposable records. No equipment-control button exists.
- Backend unavailable: after test-stack shutdown, navigation remained usable,
  health showed Disconnected, refreshed external-call count became Unavailable,
  and proof/readiness/health showed errors rather than fabricated success.

Browser accessibility/DOM inspection verified these states. Screenshot capture
was unavailable in the browser tool; no screenshot-based visual claim is made.
The original stylesheet/layout were retained with small form/data-view additions.

## Limits for later demonstration

The live query proved transport, routing, result/evidence rendering and visible
fail-closed handling. It did not prove the local model can produce a useful,
citation-valid answer for the current corpus. Do not present the controlled
approval fixtures as model-generated recommendations. Model/corpus quality and
latency must be checked when preparing the later demo; no hardcoded answer or
backend safety bypass was added to hide this limitation.

Knowledge search/local PDF ingestion are wired to existing APIs; no ingestion
write was performed during browser validation. Existing document count is not
available through an inventory endpoint and is not fabricated. Conversation
history is page-local; keep the query page open while inference runs. Auth status
is the last `/auth/me` snapshot; the backend still rechecks authority on every
protected request, including expiry/demotion and concurrent account changes.
