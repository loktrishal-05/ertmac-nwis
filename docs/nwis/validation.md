# NWIS backend validation

Validated in the isolated `ertmac-nwis-backend` Compose project, using PostgreSQL 17 / PostGIS 3.5 and Qdrant 1.17.0. Existing local BGE embedding and reranker artifacts were mounted read-only for the real retrieval check. No hosted inference or Oil India connection was used.

| Check | Result |
| --- | --- |
| NWIS domain/API/retrieval suite with `NWIS_TEST_POSTGRES=1` | 38 passed; real-model test deliberately run separately |
| Real local BGE + sparse + Qdrant RRF + BGE reranking | 1 passed |
| NWIS development benchmark | 40 passed, zero errors/failures/skips; blind subset not run |
| Existing auth/durable unit checks | 60 passed; 43 PostgreSQL cases subsequently enabled separately |
| Existing PostgreSQL security/durable checks | 42 passed on combined run; one subprocess recovery timeout passed on isolated retry |
| NWIS PostGIS checks after migration correction | 6 passed, including roundtrip, coordinates, radius/index, real HTTP lifecycle and repeat seed |
| Alembic model drift | No new upgrade operations; also passed under a restricted application schema search path |
| Staged whitespace check | Passed |
| Authorized report copy | SHA-256 matches the supplied master PDF |

These are functional checks, not measurements of clinical/industrial safety, field probability calibration, NPT reduction, AUROC or PR-AUC. Benchmark cases reuse some of the unit checks and are not 40 independent field trials.

The initial real-schema regression exposed unqualified PostGIS type resolution under a restricted search path. The new migration now installs/references PostGIS in `public`, and SQLAlchemy recognizes both reflected type names. All 22 existing PostgreSQL security cases then passed. The process-exit recovery test exceeded its existing 30-second child-process timeout while suites ran concurrently; it passed in a separate 16-second test run without altering its timeout or implementation.

The seed reproducibility/provenance test verifies stable PDF bytes, source hashes, six source pages, synthetic labels, and authorization. The telemetry regression confirms fresh sibling channels cannot validate stale torque readings. A generated report page was also visually inspected. PDF ingestion preserves page references and flags OCR numbers for review.

All historical migration files and frozen old benchmark files remain unchanged. The new benchmark has 40 development and eight held-out cases. Git attributes pin the checksum-bound JSON to LF. Main was inspected read-only; its staged/unstaged changes were not modified. No frontend files were changed, and no push or merge was performed.

Known limits and reproducible commands are in [the runbook](README.md). The earlier NWIS-B1 prompt was not available in this resumed conversation; implementation was checked against the user's current explicit scope and the complete authorized PDF.

## B2 validation (offset explanations, aligned correlation, telemetry freshness, query mode, evidence chain)

Run on 2026-09-30 in the same isolated `ertmac-nwis-backend` Compose project (PostgreSQL 17 / PostGIS 3.5, Qdrant 1.17.0, local BGE artifacts mounted read-only).

| Check | Result |
| --- | --- |
| NWIS SQLite domain/API suite (`test_nwis`, `test_nwis_b2`) | 39 passed |
| NWIS suite with `NWIS_TEST_POSTGRES=1` (all `test_nwis*.py`) | 51 run: 50 passed, 1 skipped (real-model test, run separately) |
| Real local BGE + sparse + Qdrant RRF + BGE reranking | 1 passed |
| NWIS development benchmark | 46 passed, zero errors/failures/skips; blind subset not run |
| Alembic model drift | No new upgrade operations |
| Durable/auth/security regression subset (SQLite form) | 172 run: 128 passed, 44 skipped (PostgreSQL-gated legacy cases; B2 does not change auth) |
| `git diff --check` | Passed |

B2 adds no migration. `MatchOut.explanation` is response-only (not persisted). Checksum-bound benchmark JSON is committed with LF endings and the manifest hash is computed on those bytes. These remain functional checks, not field calibration, AUROC/PR-AUC or NPT measurements.
