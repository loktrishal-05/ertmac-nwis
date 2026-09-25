# Advanced-B validation

## Recovery and preservation

Recovered on 2026-09-25 at HEAD `30c89eb` (Advanced-A3). The required first
checks were `git status --short`, `git diff --check`, `git diff --stat` and
`git log -8 --oneline`. Initial diff check passed; 21 tracked files had
127 insertions and 21 deletions, alongside untracked work.

Already present: operator-note schema/model/service, operational migration and
APIs, handover/compliance specialists, knowledge-gap and visual services,
LangGraph/query/status integration, evidence/audit/governance extensions,
Operational Workspace and 23 passing Advanced-B tests. These were reused.
Documentation and full validation were unfinished; inspection also exposed
authorization, note-integrity and gap-reporting gaps.

Preserved unrelated work, corroborated by the prior A3 validation inventory:
`.codex/`, `_incoming_phase10_bundle/`, `claudex-loop/`, Phase 9 seed/validation
scripts and regression tests, dataset-license additions, the Workspace query
timeout change, and existing Workspace evidence notice/assertions. No reset,
checkout, clean, automatic commit or Advanced-C work was performed.

## Completed in this session

- Operational query authentication now precedes replay; rejected roles return 403.
- Note review state checks its original immutable source binding. Changed notes
  become INVALID and are excluded from handover with an explicit evidence gap.
- Visual uncertainty includes ambiguous labels, conflicting candidates and
  missing drawing revisions. Terminal refusals do not invent evidence gaps.
- Gap metadata avoids raw query text, and the listing orders by run creation
  time rather than random UUIDs. Its authorization errors use the shared handler.
- Closed maintenance records are classified as recorded completed work.
- Switching operational forms clears stale results using the existing hook.
- Added HTTP, replay, integrity, incident, quality, privacy and visual regression
  coverage; updated application route/audit expectations for the new capability.
- Added the operational guide and this validation record.

## Checks

Targeted checks from `backend/`:

```powershell
$env:PYTHONPATH='tests'
.venv/Scripts/python.exe -m unittest test_advanced_b test_phase9 -q
```

**52 passed**: 33 Advanced-B tests and 19 existing Phase 9/P-204 regression tests,
11.448 seconds. P-204 uses controlled model output and real governance/evidence
fixtures; this is not a new live-model inference run. Log:
`advanced-b-targeted-final.log` (local ignored artifact).

Full backend command:

```powershell
$env:PYTHONPATH='tests'
$env:WORKBENCH_TEST_POSTGRES='1'
.venv/Scripts/python.exe -m unittest discover -s tests -q
```

**666 tests run: 665 passed, 1 skipped**, 83.763 seconds, no failures or errors.
The skipped test is opt-in live-model inference. Log:
`advanced-b-backend-verified.log` (local ignored artifact). The run includes the
final maintenance-status fix. Initial runs exposed old route/audit assumptions
and an unwanted refusal gap event, subsequently repaired. PostgreSQL was
initially stopped; Docker Desktop and the existing repository PostgreSQL service
were started. The final run executed outside the sandbox; an earlier run also
passed after PostgreSQL became available. Integration uses isolated test schemas.

PostgreSQL migration upgrades through `0013_operational_intelligence` and Alembic
schema-drift checks passed (`No new upgrade operations detected`). Existing
database immutability, approval, audit and security regression tests passed.
Offline migration SQL generation also passed in the foundation suite. No
application public-schema migration was performed.

Frontend, from `frontend/`:

```powershell
node --test --test-concurrency=1 src/services/api.test.js src/WorkspacePages.test.js src/OperationalPages.test.js
npm run lint
npm run build
```

**8 tests passed; lint and Vite production build passed.** Tests/build required
execution outside the Windows sandbox because child-process spawning returned
EPERM. Sequential test execution avoids the shared Vite HMR port collision.

Python compileall over app, migrations and tests passed. Application import,
SQLAlchemy mapper configuration and OpenAPI generation passed (38 paths).
`git diff --check` passed; checkout LF/CRLF notices are not whitespace errors.

## Frozen interface

All **101 tracked Phase 10 benchmark files are byte-identical to HEAD**.
No cases, expectations, validators, benchmark prompts or prior results changed.
No validation/blind benchmark cases ran. Existing evaluation-asset tests only
check file integrity. Three legacy retrieval fixtures use checkout CRLF and
match HEAD after line-ending normalization; their git diff remains empty.

## Change inventory

Recovered Advanced-B files include the 0013 migration; operational route,
schema, model and four service files; graph/router/state/evidence changes;
query/status/API registration; evidence integrity/sufficiency, observability,
governance, preflight and model registration; foundation expectations; and
OperationalPages component/test plus App navigation.

This session modified `app/api/routes/query.py`, `app/api/routes/operational.py`,
`app/services/operator_notes.py`, `app/services/operational_intelligence.py`,
`app/services/evidence_integrity.py`, `app/services/execution_observability.py`,
`app/services/knowledge_gaps.py`, `app/services/visual_intelligence.py`,
`tests/test_advanced_b.py`, `tests/test_agents.py`, `tests/test_phase5e.py`
(all under backend), and `frontend/src/OperationalPages.jsx`; it added both
`docs/advanced-b-*.md` files. Unrelated recovered changes were preserved.

## Limitations

See the operational guide for read caps, instantaneous exact-unit environmental
comparison, unlinked prior advisories and OCR-only visual limitations. No live
model quality/performance claim or interactive browser walkthrough is made.
Frontend checks are SSR/API-client tests and lint/build. Gaps remain OPEN; no
autonomous resolution or knowledge promotion exists. Internal roles share the
existing internal scope. Migration testing does not deploy the migration into
the application's public schema. Human review releases advice only.

Verdict: **ADVANCED-B COMPLETE**. No commit; no Advanced-C work.
