# NWIS backend implementation and runbook

This additive backend implements the SIH26121 nearby-well evidence workflow on committed base `831c149`. It resumes the existing `pivot/nwis-backend` worktree. Main and the frontend worktree are outside its scope. The authoritative specification is [the complete 79-page master PDF](reference/eRTMAC_NWIS_Master_Report_SIH26121.pdf), SHA-256 `a0de00901f40fe0d79c85a2978e41178e77dad93dafa1beb75976a040b970e65`. This copy is byte-identical to the user-authorized `docs/eRTMAC_NWIS_Master_Report_SIH26121.pdf` in main. No DOCX is required.

## Report understanding

NWIS supplies eRTMAC with historical offset-well memory. Its vertical slice is active well -> indexed radius search -> explainable offset ranking -> depth/formation evidence -> hazard look-ahead -> engineer review. The report requires provenance, separate probability and confidence, explicit missing data, synthetic labeling, bounded queries, local retrieval and an advisory-only safety boundary. The model must not create probabilities or operate drilling equipment. No refinery-specific document supplies NWIS requirements.

## Start the isolated stack

Run commands from this worktree's root. Docker Desktop must be running. This Compose project uses its own PostGIS/Qdrant volumes and does not attach old product database volumes. The backend listens only on `127.0.0.1:8011`. The default database password is for isolated local synthetic development only; set `NWIS_DB_PASSWORD` for any shared environment.

```sh
docker compose -f infra/docker-compose.nwis.yml build backend
docker compose -f infra/docker-compose.nwis.yml up -d postgres qdrant
docker compose -f infra/docker-compose.nwis.yml run --rm --no-deps backend python -m alembic -c backend/alembic.ini upgrade head
docker compose -f infra/docker-compose.nwis.yml run --rm --no-deps backend python -m scripts.seed_nwis --generate
docker compose -f infra/docker-compose.nwis.yml run --rm --no-deps backend python -m scripts.seed_nwis
docker compose -f infra/docker-compose.nwis.yml run --rm --no-deps backend python -m scripts.seed_dev_users
docker compose -f infra/docker-compose.nwis.yml up -d backend
```

The reused development-user script creates `dev_requester` / `dev-requester-pass-1` and `dev_reviewer` / `dev-reviewer-pass-1`. These are local-only test identities, never production accounts. Login uses the existing `/auth/login` session cookie contract. Then POST `/api/terms/accept` with `{"version":"nwis-advisory-v1","accepted":true}`. Requesters may inspect wells/evidence and assess risk; reviewers also replay data, review advisories and validate extracted events; admins may ingest reports. Restricted wells are admin-only. Browser writes use the existing same-origin guard.

## Data and provenance

`data/nwis_demo/dataset.json` is deterministic ground truth: 12 synthetic wells, 48 formation intervals, 396 survey stations, 66 events in 11 six-page WCR/DDR reports, and 610 telemetry samples across 10 channels. Every source record carries `dataset_origin="synthetic_demo"`. This is not Oil India data. `--generate` regenerates JSON and PDFs under `data/nwis_demo/reports/`; the normal seed can generate its ground truth without those files. Seeding is repeatable and refuses non-demo identity collisions. PDF hashes, rather than invented source hashes, are persisted. Source files are stored by hash under `data/nwis/reports/` and served through an authorized endpoint.

MD, TVD and TVDSS remain distinct. Missing survey/datum values stay null; interpolation never extrapolates. PostGIS stores `geography(Point,4326)` with a GiST index and a coordinate synchronization trigger. PostGIS is installed in `public`; its type/functions are schema-qualified so migrations also work under isolated application schema search paths. The deployed query uses `ST_DWithin` and meter-based `ST_Distance`. Only isolated SQLite tests use a spherical distance fallback.

## API contract

OpenAPI is available at `http://127.0.0.1:8011/docs`. Lists expose `items`, `limit`, `offset`, `has_more` and `as_of`.

| Endpoint | Purpose |
| --- | --- |
| GET `/api/wells`, `/api/wells/{id}` | Well inventory/context |
| GET `/api/wells/{id}/formations` | Paginated formation intervals |
| GET `/api/wells/{id}/nearby?radius_km=10` | Similarity-ranked offsets with raw distances and component scores |
| GET `/api/wells/{id}/correlation` | Active/offset formations and events |
| GET `/api/events?well_id=&formation=&type=&depth_basis=tvd&depth_min=&depth_max=` | Source-backed event search |
| GET `/api/reports/{id}/source` | Authorized, hash-verified PDF; append `#page=N` in the viewer |
| GET `/api/wells/{id}/risk?lookahead_m=100` | Read-only risk for 50/100/150 m |
| POST `/api/wells/{id}/assess` | Persist assessment/evidence and evaluate alert policy |
| GET `/api/wells/{id}/telemetry?channels=torque&from=&to=` | Bounded time window, at most 24 hours |
| POST `/api/wells/{id}/replay` | Reviewer selects an exact synthetic timestamp |
| POST `/api/query` | Durable four-agent evidence workflow |
| GET `/api/advisories` | Review queue |
| POST `/api/advisories/{id}/review` | Acknowledge/dismiss/review with reason |
| POST `/api/events/{id}/validate` | Reviewer validation/rejection with reason |
| POST `/api/ingest/report?well_id=&type=DDR&dataset_origin=` | Admin PDF ingestion, `application/pdf`, max 20 MiB |
| GET `/api/audit` | Reviewer-owned/admin-wide NWIS audit entries |

`/api/query` requires a UUID `request_id` and a nonempty `query`. Optional fields include `well_id`, `formation`, `type`, `depth_min`, `depth_max`, `depth_basis`, `radius_km`, `lookahead_m`, `top_k`, and `retrieval` (`structured` or `hybrid`). Reuse a request ID only to resume/retrieve the same request; use a new ID after changing context or evidence. Checkpoint replay reauthorizes evidence and rejects changed cited events.

## Similarity and risk

Default similarity weights are geographic .15, formation .30, depth .20, trajectory .15, program .10, data quality .10. Geography is `exp(-distance_m/5000)`; formation is an unambiguous canonical match; depth is overlap of the active look-ahead interval with the matching offset formation, preferring TVDSS then TVD then MD. Trajectory compares inclination; program compares available mud/hole/casing attributes. Unknown components remain null and contribute zero; MD-only comparison reduces quality. `NWIS_OFFSET_WEIGHTS` accepts a JSON object with those six nonnegative weights and normalizes their sum. These are prototype engineering choices, not learned or calibrated coefficients.

Risk combines similarity-weighted offset event prevalence with a bounded .15 persistent telemetry modifier. Per-channel quality and freshness gates prevent stale/invalid readings from contributing. Robust deviation uses a local baseline and three-sample persistence. Confidence reports analog count, quality, evidence confidence, telemetry availability, contradictions and depth basis. Contradictory accounts reduce confidence. No usable offsets yields null probability. The JSON field `probability` is explicitly `calibrated=false`; it is a heuristic exposure score, not a validated field-event probability.

Alerts require score >= .6, confidence >= .5, two supporting wells and three successive assessments. Clear threshold is .4; cooldown is 30 minutes. Same/older timestamps cannot advance persistence, and gaps over five minutes reset it. Assessments are serialized per well. Review records capture user, time, reason and evidence IDs in the reused hash-chained audit trail. Approval never invokes equipment.

## Retrieval and agents

The four LangGraph nodes are Offset Well Agent, Well Knowledge Agent, Drilling Risk Agent and Advisory Agent. They reuse SQL checkpoints and execution locks. The advisory uses a deterministic cited template and accurately records that model route; it does not pretend to have called Qwen. It may return insufficient evidence.

Hybrid mode reuses local BGE embeddings, sparse encoding, Qdrant, reciprocal-rank fusion and the BGE cross-encoder. Its separate `nwis_evidence_v1` collection contains authorized event/report/page/depth/formation metadata and content snapshots. Relational authorization happens before retrieval, and stale indexed facts are rejected. Structured retrieval works without model artifacts; requesting hybrid mode fails explicitly if its dependencies are unavailable.

Set `NWIS_MODEL_DIR` to an existing local model directory containing `bge-base-en-v1.5` and `bge-reranker-base`. For example in PowerShell: `$env:NWIS_MODEL_DIR='C:/path/to/models'`. It is mounted read-only. Then index:

```sh
docker compose -f infra/docker-compose.nwis.yml run --rm --no-deps backend python -m scripts.seed_nwis --index
```

After ingestion or event validation, re-run indexing before hybrid retrieval. Existing embeddings are cached by content hash. Native PDF extraction reuses Docling/PyMuPDF and the existing bounded local OCR fallback. The conservative extractor understands explicit event/depth/unit fields and retains uncertain free text for review; it is not a general trained drilling NER model. OCR numeric values cannot become risk evidence without corrected source ingestion and review.

## Deterministic demo

1. Login as the local reviewer and accept NWIS terms.
2. Inspect `ACTIVE-01`, its formations and offsets. The closest `OFF-01` is less relevant than formation-matched `OFF-04` and `OFF-09`.
3. Inspect a 100 m look-ahead and open source PDFs using event `source_report_id` and `source_page`.
4. POST replay bodies `{"as_of":"2026-09-29T15:58:00Z"}`, then `15:59:00Z`, then `16:00:00Z`; POST `/api/wells/ACTIVE-01/assess` after each replay.
5. Open `/api/advisories`, acknowledge one with `{"status":"acknowledged","reason":"Reviewed the synthetic source evidence"}`, and inspect `/api/audit`.

Replay freshness is relative to its historical assessment timestamp and is labeled as replay, not live eRTMAC. A repeated demo on already-persisted timestamps is deliberately idempotent and may return existing advisories rather than new ones.

## Validation

```sh
docker compose -f infra/docker-compose.nwis.yml run --rm --no-deps -e NWIS_TEST_POSTGRES=1 backend python -m unittest discover -s backend/tests -p 'test_nwis*.py' -v
docker compose -f infra/docker-compose.nwis.yml run --rm --no-deps -e NWIS_TEST_RETRIEVAL=1 backend python -m unittest test_nwis_retrieval.RealRetrievalTests -v
docker compose -f infra/docker-compose.nwis.yml run --rm --no-deps backend python -m scripts.benchmark_nwis
docker compose -f infra/docker-compose.nwis.yml run --rm --no-deps backend python -m alembic -c backend/alembic.ini check
```

PostGIS tests create/drop a uniquely named validation database only through the dedicated `nwis` target. They exercise upgrade/downgrade, the spatial index, exact radius boundaries, real login, replay/assessment/review and audit. See [validation results](validation.md) for the checks performed on this change. The 46 development benchmark cases and eight held-out cases live in `benchmark/nwis/`; old benchmark files remain frozen. Held-out cases are not used for tuning.

## Explicit prototype limits

This implements the report's backend demonstrator, not its future production program. There is no trained/calibrated hazard classifier, live WITSML/ETP transport, OSDU service, downhole spatial query, automatic rig control, or claimed NPT reduction. The WITSML interface is a local-replay adapter boundary. Similarity/risk currently evaluates the active canonical formation; multi-formation transition forecasting and datum reconciliation need validated domain data. The API does not silently infer geological continuity. Surface radius candidates are capped at 500, correlation at 200 intervals/500 events, and retrieval at 500 events; narrower queries are required above these bounds. Deployment, frontend integration and merging are separate tasks. Historical migrations and generic auth/security infrastructure are retained.

The frozen B2 frontend integration contract, including exact schemas, nullable fields, role gates and ordering, is [backend_api_contract.md](backend_api_contract.md).
