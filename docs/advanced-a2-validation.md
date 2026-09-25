# Advanced-A2 validation

## Recovered state and scope

Started from `7d16d70` (Advanced-A1), with existing unrelated modifications to the dataset-license manifest and two frontend files, plus pre-existing local tooling, incoming assets and Phase 9 scripts/tests. These were preserved. No benchmark or A1 registry/validator changes were made.

## Targeted validation

From repository root, using the existing backend virtual environment:

```powershell
$env:PYTHONPATH='backend;backend/tests'
backend/.venv/Scripts/python.exe -m unittest test_advanced_a2 -q
```

**29 tests passed** in 9.087 seconds. Tests cover A1 precedence, deterministic-first routing, preflight/injection/scope boundaries, strict planner outputs and unavailable model fallback, CAG approval and candidate rejection, source hash/revision changes, member staleness/revocation/scope changes, metadata binding, ambiguous matches, preserved citations, Hybrid graph reuse, HITL enforcement, authenticated mutation and audit-chain verification after pack revocation. Model calls use controlled doubles; no model was downloaded or benchmark run performed.

## Full backend validation

From `backend/`:

```powershell
$env:PYTHONPATH='tests'
$env:WORKBENCH_TEST_POSTGRES='1'
.venv/Scripts/python.exe -m unittest discover -s tests -q
```

**608 tests run: 607 passed, 1 skipped**, in 72.174 seconds. The skipped test is the opt-in live-model test. No failures.

The PostgreSQL-enabled tests exercise migration to the new head and metadata consistency in isolated test schemas. Existing A1 live registry/approval/audit integration also runs. CAG-specific lifecycle tests use the real service/ledger on SQLite with controlled Qdrant evidence and temporary source files; a live CAG/model end-to-end demonstration was not performed. Validation does not migrate the main application schema automatically.

## Additional checks

- `python -m compileall -q backend/app backend/alembic backend/tests`: passed.
- `git diff --check`: passed; Git's LF-to-CRLF notices are line-ending warnings.
- All **101 tracked benchmark files** compared byte-for-byte against HEAD: unchanged.
- No validation/blind benchmark inference, commits or Advanced-A3 work.

## Files in this change

Existing files: `backend/app/agents/graph.py`, `backend/app/api/router.py`, `backend/app/api/routes/query.py`, `backend/app/core/config.py`, `backend/app/db/models/__init__.py`, `backend/tests/test_foundation.py` (expected metadata table count).

New files: `backend/alembic/versions/0012_knowledge_packs.py`, `backend/app/db/models/knowledge_pack.py`, `backend/app/services/knowledge_packs.py`, `backend/app/services/adaptive_execution.py`, `backend/app/api/routes/knowledge_packs.py`, `backend/tests/test_advanced_a2.py`, and the two Advanced-A2 documentation files.

## Limits

Trusted paths are internal-only and deliberately narrow. Pack invalidation is on access; packs are immutable and replacements require fresh approval. CAG is reviewed context composition, with no KV-cache performance claim. Optional System-1 is disabled by default; full graph model-call totals are not available. Governed replay bodies retain their existing shape, while adaptive metadata is logged. See `advanced-a2-adaptive-routing.md` for configuration and API contracts.
