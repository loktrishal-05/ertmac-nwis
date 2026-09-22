# Phase 6 validation

## Result

PHASE 6 COMPLETE. No remaining BLOCKER/HIGH issue identified in this scope.
No commit created; no Phase 7 work, frontend change, or database schema change.
Pre-existing Phase 5F repairs and unrelated working-tree changes were preserved.

## Executed tests

From `backend`, using the existing `.venv`, with `PYTHONPATH=tests`:

| Validation | Result |
| --- | --- |
| Full backend: `WORKBENCH_TEST_POSTGRES=1 python -m unittest discover -s tests -v` | 513 run, 512 passed, 1 skipped; 133.457 seconds |
| Final focused: `python -m unittest test_phase6 test_pid test_hybrid test_agents test_agents_maintenance -v` | 133 passed; 31.412 seconds |
| Phase 6 within final focused run | 21 passed |
| `python -m compileall -q app tests` | PASS |
| `git diff --check` | PASS |

The full run preceded the final artifact-header binding guard and two added
tests (graph propagation and artifact substitution); the final 133-test run
verified that final code. Totals overlap and must not be added as unique tests.
Local detailed output remains in ignored `phase6-test-results.log` and
`phase6-targeted-results.log` at repository root.

The sole full-suite skip was the opt-in live local-model `/query` smoke test.
PostgreSQL suites were enabled and ran against real PostgreSQL in disposable
schemas, including Phase 5D evidence and Phase 5F authorization/concurrency
probes. Their migration metadata checks reported no new upgrade operations.
Phase 6 adds no migration. Qdrant/Ollama/live OCR inference were not needed:
the changed path reads existing artifacts; retrieval/model boundaries use
the existing test infrastructure. This is not a claim of live OCR accuracy.

## Regression coverage

The full run includes Phase 3B1 P&ID processing, Phase 3B2 hybrid retrieval,
Phase 4 agents/repair tests, Phase 5A–5F security/governance tests, PostgreSQL
tests, and benchmark asset guards. No regression failed.
The final focused run repeats P&ID, hybrid retrieval, registry/graph, and
Maintenance regressions after the final changes.

An existing Knowledge test was intentionally updated: low-confidence OCR
remains ambiguous even when its candidate matches the equipment registry.
That matches the explicit Phase 6 uncertainty requirement.

## Phase 6 assertions

The 21 tests in `backend/tests/test_phase6.py` cover:

- High confidence stays unverified; low confidence stays ambiguous.
- Raw OCR and normalized candidate remain separate.
- Drawing/version, revision, page, region, bounding box, and OCR marker survive.
- Unreadable line size refuses; valve labels never claim completeness.
- OCR cannot prove isolation, valve state, or authorize action.
- Knowledge consumes the real region adapter; LangGraph preserves evidence
  and records the existing tool invocation.
- Safety requires procedural evidence and retains HITL despite model approval.
- Maintenance cannot diagnose from OCR alone.
- Missing/malformed artifacts fail closed.
- Phase 5D binds OCR provenance and permits exact approved advisory release.
- Mutated OCR candidate, changed source bytes, and substituted artifact version
  each deny release after approval.
- Non-drawing queries skip lookup; identifier-miss drawing queries still refuse.

Fixtures reuse Phase 3B1 detection grouping and artifacts plus the existing
Phase 5D governance fixture. They contain synthetic drawing bytes and OCR
results; they do not invoke a second OCR implementation.

## Scope

IMPLEMENTED: P&ID OCR evidence integration into the existing agentic/RAG path.

NOT IMPLEMENTED: verified knowledge cache, semantic answer cache, voice,
multilingual, BI, fine-tuning, new agents, workflows, or automatic plant control.

Topology, connectivity, flow direction, valve state, isolation, permit status,
and equipment readiness cannot be established by OCR. Drawing evidence remains
supporting evidence, and approval releases an advisory response only.
