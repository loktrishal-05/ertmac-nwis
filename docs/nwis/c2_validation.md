# C2 executed validation

Date: 2026-09-30. Base: `70f90606346e81c4c36f916be967a2d4cecc541a`. Worktree: `ertmac-nwis-backend-c2`; branch: `pivot/nwis-backend-c2`. Separate Compose project `ertmac-nwis-backend-c2`, loopback API 8012, dedicated PostgreSQL/Qdrant volumes, existing local BGE artifacts mounted read-only. Frozen B2 source, migrations, seed and API contract are unchanged. No frontend work, push, merge, deployment or held-out benchmark execution.

## Tests actually executed

Use the `$c2` Compose arguments in [demo_runbook.md](demo_runbook.md); commands below were executed with those two `-f` arguments explicitly.

| Command after `docker compose @c2` | Result |
| --- | --- |
| `exec -T -e NWIS_TEST_POSTGRES=1 backend python -m unittest test_nwis test_nwis_b2 test_nwis_c2 test_nwis_postgres test_nwis_retrieval -v` | 55 run; 54 passed, 1 real-model case skipped for separate execution; 117.953 s. C2 then contained four tests. Includes all six real PostGIS cases. |
| `exec -T -e NWIS_TEST_RETRIEVAL=1 backend python -m unittest test_nwis_retrieval.RealRetrievalTests -v` | 1 passed; real BGE/sparse/Qdrant/RRF/reranker; 43.584 s including model loading. |
| `exec -T backend python -m unittest test_phase5b.AuthHTTPTests test_phase_f_auth -v` | 53 passed; 15.337 s. OAuth/SMTP tests use existing in-process mocks; no provider was enabled or contacted. |
| `exec -T backend python -m unittest test_nwis_c2 -v` | Final five C2 tests passed; 11.354 s. Four reruns plus added missing-current-depth check. |
| `exec -T backend python -m alembic -c backend/alembic.ini check` | No new upgrade operations detected. |
| `exec -T backend python -m scripts.validate_nwis_runtime` | Passed: readiness, migration, extension, spatial index/query/order, two reseeds, all domain origins, 11 source hashes, audit chain, Qdrant and local artifacts. |
| Real HTTP `scripts.smoke_nwis_demo.run(..., hybrid=True)` | First complete run: 63 HTTP checks passed, plus ten authorized PDF/hash checks; no dependency overrides. |

**109 distinct test cases passed**, accounting for the separately enabled real-model case and final added depth case. Repeated runs are not counted as new coverage. The combined suite's one skip was subsequently executed successfully. The development benchmark was unnecessary; the eight held-out cases were not opened or executed.

The first smoke used a generated private password and the existing provisioning function to create `nwis_c2_validation` as reviewer, then called `run('http://127.0.0.1:8000', username, password, 'data/nwis_c2_smoke.json', hybrid=True)` inside the C2 backend container. The CLI performs the same flow with a hidden password prompt. The final fixture-pinned repeat smoke passed 62 HTTP checks plus ten PDF/hash checks, emitted [0, 0, 0] new advisories, and retained the existing acknowledgement. No password/session cookie appears in committed output. The team account is provisioned by the runbook; there are no shared hard-coded demo credentials.

## Runtime and PostGIS evidence

`/ready`: HTTP 200, `status=ready`; fastapi/configuration/postgresql/qdrant/model all true. Model check is runtime reachability and configured `qwen3.5:9b` presence, **not Qwen inference**. Local BGE and reranker inference was exercised separately and over HTTP hybrid queries. Optional OCR/speech/Google/SMTP are outside the golden path; Google/SMTP are disabled. The synthetic telemetry source is replay, not a live eRTMAC feed.

Migration upgrade succeeded at `0018_nwis`; real PostGIS extension **3.5.2** on PostgreSQL 17. Index:

```sql
CREATE INDEX ix_nwis_wells_location ON public.nwis_wells USING gist (location);
```

Executed SQL (the validator records the same SQL and parameters):

```sql
SELECT w.id, ST_Distance(a.location,w.location) AS distance_m
FROM nwis_wells a JOIN nwis_wells w ON w.id <> a.id
WHERE a.id=:active AND ST_DWithin(a.location,w.location,:radius)
AND w.access_scope IN ('internal','public')
ORDER BY distance_m,w.id LIMIT :limit OFFSET :offset;
```

Parameters: `active=ACTIVE-01`, `radius=10000`, `limit=100`, `offset=0`. Two executions returned the same 11 rows:

| Well | Distance m |
| --- | --- |
| OFF-01 | 148.52676803 |
| OFF-02 | 773.64911852 |
| OFF-03 | 1160.46976544 |
| OFF-04 | 1547.28780373 |
| OFF-05 | 1934.10323313 |
| OFF-06 | 2320.91605333 |
| OFF-07 | 2707.72626405 |
| OFF-08 | 3094.53386500 |
| OFF-09 | 3481.33885590 |
| OFF-10 | 3868.14123645 |
| OFF-11 | 4254.94100637 |

With `SET LOCAL enable_seqscan=off`, EXPLAIN contained `Index Scan using ix_nwis_wells_location`, `_st_expand(...,10000)`, and `st_dwithin(...,10000,true)`. This proves index availability; it does not assert that the planner must prefer an index on a 12-row table. Existing real-PostGIS tests also passed the +/-0.01 m radius boundary and coordinate trigger checks. API nearby ordering is **score descending, ID ascending**, distinct from this distance order.

Two repeat seeds preserved: **12 wells, 396 trajectory points, 48 formation intervals, 11 reports, 66 events, 610 telemetry samples**. Domain origins remained `synthetic_demo`. All 11 content-addressed report files matched stored SHA-256. Reseed intentionally appends audit entries and does not reset assessments/reviews.

Qdrant `nwis_evidence_v1`: **green**, **66 points**. Local embedding config/weights and reranker config/weights present. Hybrid HTTP queries returned cited event/report/page/depth/formation metadata, including an explicitly constrained `OFF-04`/`TIPAM_A` query. The separate real retrieval unit check also passed with actual artifacts and server Qdrant. No hosted embedding/model service was used.

## Evidence, alerts and authorization

The fixture and runbook contain all ten stuck-pipe evidence IDs, depths, source links and snapshot hashes. Golden events remain `unverified` after assessment, query and advisory acknowledgement. C2 mutations occur only in isolated test fixtures:

- Rejected/review_needed events are excluded even at .9 confidence.
- .499 confidence is excluded for both unverified and validated events; eligible unverified events at .5 may contribute.
- Current verification state remains visible; previous `event_at_assessment` state/confidence and source hashes are preserved.
- Only explicit human validation changes the event to validated; actor/time/reason are audited.
- Requester review returns 403 and does not change the advisory. Real HTTP unauthenticated review returns 401; duplicate review 409; reviewer ingestion 403.

On fresh runtime state, the 15:58/15:59/16:00 replay-assess sequence emitted **0, 0, 2** advisories. Repeated assessment emitted none. B2 hysteresis/cooldown test passed: .5 retains active alert, .3 clears, attempts inside cooldown suppressed, re-alert allowed at minute 32 following first alert at minute 2. C2 transient high/low test resets persistence and does not spam. All original thresholds and identity rules are unchanged.

Stuck-pipe advisory `c89611d1af0c729b9c476ecdbc275a62e4e26f04714b091f246a94905401e1c6` was acknowledged for assessment `1082674d59e85dc8b1f57843ddb690ef92c23f5e565e1665358a036ad1b9abd7`. Reviewer identity `5b4287fb-9a54-4d03-a391-108813d27ce9` and time `2026-09-30T01:05:25.162367Z` were returned and preserved. These are observed validation-run IDs; integrations must use returned IDs rather than hard-code them.

Own-audit HTTP checks found `demo_reviewer_provisioned`, `terms_accepted`, `telemetry_replay_seek`, `risk_assessed`, `knowledge_query` and `advisory_review`. Every returned audit actor matched the reviewer. After the first smoke and reseed checks, full database audit verification passed **26 entries**, sequences 1..26, no error. After the repeated smoke and final runtime validation, full-chain verification passed **44 entries**, sequences 1..44, no error; head hash `c8aacd4d686b96f04eca7e828cdf93fe3356ccd8f963b9b11f3498a2c0bfe788`.

## Local performance and limitations

Three warm TCP samples per operation on local Docker; fresh UUIDs for every measured query:

| Endpoint | First-run median ms | Repeat median ms |
| --- | --- | --- |
| Wells | 24.43 | 21.80 |
| Nearby | 403.44 | 259.54 |
| Correlation (100 m) | 286.27 | 300.52 |
| Risk (100 m) | 557.81 | 339.19 |
| Assessment detail | 97.58 | 109.23 |
| Telemetry | 123.11 | 207.83 |
| Hybrid knowledge query | 6999.01 | 3230.36 |

Hybrid CPU retrieval showed 3.23-7.00-second warm medians across the two runs; warm it before presenting. Other measured endpoints stayed below .6 seconds. These are local sanity measurements, not throughput guarantees. C2 limits OpenMP/MKL to two threads for predictable local resource use and changes no B2 algorithm. BGE cold startup is included in the separate 43.584-second retrieval test, not in the warm query median.

During C2 development, an initial smoke assertion incorrectly expected OFF-09 to rank second; observed frozen ranking is OFF-04/OFF-02/OFF-03/OFF-09. The script was corrected without changing seed/scoring. A validator cleanup error (QdrantClient lacks context-manager support) was corrected using stdlib `closing`. Both were new C2 tooling defects; completed reruns passed. No B2 regression or API blocker was found. Existing dependency deprecation/resource warnings were non-fatal.

Risk remains uncalibrated, synthetic, advisory only. Replay freshness is relative to the historical assessment time. Acknowledged advisory review does not validate source events. Repeating with a different reviewer requires a fresh rehearsal project for a new acknowledgement; old history is preserved. No Oil India data, live field integration, deployment, or benchmark result is claimed.
