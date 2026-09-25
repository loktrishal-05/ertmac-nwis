# Advanced-A3 validation

## Recovered baseline

HEAD was `6c96ced` (Advanced-A2). Five A2 supporting files were already untracked: the 0012 migration, pack routes/model/services and adaptive selector. They were retained; only the selector needed A3 routing changes. The dataset-license change, existing Workspace frontend changes, Phase 9 scripts/tests, `.codex/`, `claudex-loop/` and incoming bundle were preserved. No commit was made.

## Targeted backend checks

```powershell
$env:PYTHONPATH='backend;backend/tests'
backend/.venv/Scripts/python.exe -m unittest test_advanced_a3 -q
```

**26 passed**, 5.499 seconds. Coverage includes group bounds, original source identity/revisions/hash/locator preservation, rejected invented references and invented intermediate content, original-reference final citations, bounded raw-evidence fallback, stale/revoked/changed sources, OCR confidence and existing S3 fallback, untrusted injection placement, sufficiency states, missing citations/critical categories, routing precedence, planner restrictions, governance independence, graph/tool reuse, persisted replay metadata and failed-call accounting/context cleanup.

Advanced-A2 regression checks also passed: **29 tests**. Gateway doubles were used for deterministic generation tests; local model prose/performance was not benchmarked.

## Full backend

From `backend/`:

```powershell
$env:PYTHONPATH='tests'
$env:WORKBENCH_TEST_POSTGRES='1'
.venv/Scripts/python.exe -m unittest discover -s tests -q
```

**634 tests run: 633 passed, 1 skipped**, in 79.776 seconds. The skipped test is the opt-in live-model test. No failures. After the final path-label consistency adjustment, all 26 targeted A3 tests passed again.

PostgreSQL-enabled schema/integrity tests ran, including existing A1/A2 and Phase 9/security/governance regressions. The P-204 tests exercise existing sensor/SOP/maintenance/P&ID source identity, OCR limitations, advisory approval/rejection/revocation and audit behavior with controlled generation. No new live P-204 inference or browser walkthrough was performed in A3.

## Frontend

From `frontend/`:

```powershell
node --test src/services/api.test.js src/WorkspacePages.test.js
npm run lint
npm run build
```

**7 tests passed**; lint passed; Vite production build passed. Added SSR assertions cover absent metadata, MGS/partial coverage, missing evidence, model/latency, fallback, authority disclaimer and omission of unknown private-reasoning fields from the execution panel. Existing Workspace changes were preserved.

## Additional validation

- Python compileall over `backend/app`, `backend/alembic`, `backend/tests`: passed.
- Application import and OpenAPI generation: passed (34 paths).
- `git diff --check`: passed. LF/CRLF notices are not code failures.
- All 101 tracked benchmark files compared byte-for-byte with HEAD: unchanged.
- No benchmark validation/blind cases, model downloads, commit or Advanced-B work.

## Change inventory

New A3 files: `backend/app/agents/nodes/mgs.py`, `backend/app/services/evidence_sufficiency.py`, `backend/app/services/execution_observability.py`, `backend/tests/test_advanced_a3.py`, and both `docs/advanced-a3-*.md` files.

Modified for A3: graph, knowledge node, tool registry instrumentation, graph state, tracing, query route/schema, governance response metadata plumbing, gateway instrumentation, the pre-existing adaptive selector, and Workspace result rendering/tests. No governance policy, approval authority, citation validator, benchmark truth or original P-204 implementation was changed.

## Limits and operational notes

MGS is bounded document synthesis; complex operational multi-agent work remains Agentic. Sources are rechecked but are not a distributed snapshot. Intermediate extracts are checked literally; final semantic entailment still needs review. Sufficiency is conservative rule-based coverage, not safety confidence. Live-model quality/latency remains unmeasured. Execution counters measure gateway calls, not opaque transport retries or embedding/reranker calls. Existing optional tracing settings apply to informational persistence; governed replay metadata is persisted atomically in the existing run-step table. The A2 migration remains required for deployment; A3 introduces no database migration.
