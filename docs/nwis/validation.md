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

## B2 completion verification and implementation audit

The resumed worktree already contained committed B2 implementation `a9949c5`. Completion adds the actual backend API contract; no further backend behavior changes were necessary. The earlier B2 suite/benchmark/regression counts above are retained results, not claims that those large suites were rerun during documentation completion.

Fresh completion checks on 2026-09-30: focused `test_nwis_b2.B2Tests` **12 passed**; Alembic upgrade head succeeded; running PostgreSQL returned PostGIS 3.5, migration `0018_nwis`, and **11** offsets within 10,000 m of ACTIVE-01 through actual `ST_DWithin`. No host database port is published by the isolated Compose file. The focused hybrid unit case uses local Qdrant with test embeddings; the separately recorded real BGE/server retrieval check above is distinct.

Commands executed from the isolated worktree (PowerShell):

```powershell
docker compose -f infra/docker-compose.nwis.yml run --rm --no-deps backend python -m unittest test_nwis_b2.B2Tests -v
docker compose -f infra/docker-compose.nwis.yml run --rm --no-deps backend python -m alembic -c backend/alembic.ini upgrade head
docker compose -f infra/docker-compose.nwis.yml run --rm --no-deps backend python -m scripts.seed_nwis
docker compose -f infra/docker-compose.nwis.yml exec -T postgres psql -U nwis -d nwis -c "SELECT PostGIS_Version(); SELECT version_num FROM alembic_version; SELECT count(*) AS nearby_count FROM nwis_wells a JOIN nwis_wells b ON a.id <> b.id AND ST_DWithin(a.location,b.location,10000) WHERE a.id='ACTIVE-01';"
```

Audit below is based on code, not report promises. I = implemented, P = partial, M = missing. B1 status was inspected before modification; final status is constrained by the explicit prototype limits. File aliases: `M` = backend/app/db/models/nwis.py; `S` = backend/app/services/nwis.py; `R` = backend/app/api/routes/nwis.py; `K` = backend/app/services/nwis_knowledge.py; `A` = backend/app/agents/nwis.py; `T` = backend/app/services/nwis_telemetry.py. Test aliases are backend/tests/test_nwis.py (`N`), test_nwis_b2.py (`B2`), test_nwis_postgres.py (`PG`), test_nwis_retrieval.py (`Q`).

| Feature | B1 | Implemented (B2) | Partial | Missing | Files | Tests |
| --- | --- | --- | --- | --- | --- | --- |
| Wells | I | Yes | — | — | M/R | N seed/RBAC, PG HTTP |
| PostGIS | I | Yes | — | — | M, migration 0018 | PG geography/index |
| Nearby radius search | I | Yes | — | — | S/R | N ranking, PG radius |
| Trajectories | I | Stored/interpolated | No standalone survey API | — | M/S | N depth, B2 correlation |
| Formation intervals | I | Yes | — | — | M/R | N/B2 correlation |
| Formation correlation | P | Common datum/tracks/context | Missing markers explicit | — | S/R | B2 alignment/missing markers |
| Drilling events | I | Yes | — | — | M/R | N filters, B2 provenance |
| WCR/DDR extraction | P | Explicit-field parsing/review | General narrative NLP not implemented | — | K | N extraction, B2 signed depth/review |
| Synthetic dataset | I | Deterministic | — | — | scripts/seed_nwis.py | N seed, PG repeat seed |
| Offset similarity | I | Six scores, total, explanations | — | — | S | N ranking, B2 explanation/tie |
| Risk look-ahead | I | Deterministic 50/100/150 | Uncalibrated active-formation heuristic | — | S/R | N determinism, B2 chain |
| Telemetry replay | P | Bounded API/freshness/seek | Synthetic historical replay | — | T/S/R | N windows, B2 freshness |
| Telemetry anomaly features | I | Explainable window statistics | — | — | S | N persistence, B2 bad samples/gaps |
| Alert persistence | I | Three eligible assessments | — | — | M/S | N alerts, B2 chain |
| Hysteresis | I | .6 trigger/.4 clear | — | — | S | N alert policy |
| Cooldown | I | 30 minutes | — | — | S | N alert policy |
| Deduplication | I | Timestamp/assessment/interval | — | — | M/S | N alerts/idempotence |
| Evidence links | P | Persisted detail/source snapshots | Chunk link nullable for structured risk | — | M/S/R | B2 complete chain |
| Advisories | I | Cited template/review/feedback | — | — | M/S/A/R | B2 chain, PG HTTP |
| NWIS RAG/query mode | P | Explicit mode + structured/hybrid | Local model artifacts required for hybrid | — | A/K/R | B2 query/citations, Q real retrieval |
| LangGraph agents | I | Four distinct roles | — | — | A | N durable query, B2 mode |
| Audit | I | Hash-chained, role-filtered | — | — | S/R, generic audit | N/PG/B2 chain |
| RBAC | I | Requester/reviewer/admin + terms | Shared demo provisioning deferred | — | R, generic auth | N RBAC/scope |
| Benchmark | I | 46 development, 8 held out | Held-out set not run | — | benchmark/nwis | benchmark runner |
| Docker/PostGIS runtime | I | Actual migration/seed/spatial checks | No live Oil India integration | — | infra/docker-compose.nwis.yml | PG + runtime SQL above |

The API freeze is [backend_api_contract.md](backend_api_contract.md). Synthetic data is not deployed at Oil India, is not live eRTMAC, and exposes only a WITSML/ETP-ready adapter boundary. No automatic drilling control or feedback learning exists. Real OIL validation/calibration is required before operational use.
