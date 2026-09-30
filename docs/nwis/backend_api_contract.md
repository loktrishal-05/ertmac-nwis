# NWIS backend API contract ? B2

Backend truth for SIH26121 eRTMAC-NWIS, frozen from `a9949c5` (accepted B1 baseline `ec7dcdb`). This document describes the isolated backend, without consulting the frontend branch. Schema tables below are extracted from the actual FastAPI OpenAPI models; operational semantics are checked against routes/services.

## Authentication and browser integration

Use the existing session cookie from `POST /auth/login`; send browser requests with credentials. Never send a client-selected role or expose `local_admin`. `GET /auth/me` reads the authenticated identity; `POST /auth/logout` revokes the session. Browser writes must pass the existing configured Origin/Referer check. `/api/` responses use `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.

All NWIS data endpoints require an active authenticated user AND acceptance of `nwis-advisory-v1`. Read `GET /api/terms`, then POST `{"version":"nwis-advisory-v1","accepted":true}` to `/api/terms/accept`. These two endpoints require authentication but not prior acceptance.

| Role | Actual capabilities |
| --- | --- |
| requester | Wells, map inputs, correlation, events, telemetry, risk, assessment persistence, query, advisories and authorized PDFs |
| reviewer | Requester capabilities plus replay, event validation, advisory review, own NWIS audit entries |
| admin | Reviewer capabilities plus report ingestion, restricted wells, all NWIS audit entries |

There is no `viewer` or `engineer` role literal: map those UI personas to requester/reviewer. Internal/public wells are visible to requesters/reviewers; restricted wells require admin. Inaccessible single resources return 404. Lists are authorization-filtered. The existing opt-in `python -m scripts.seed_dev_users` path is for isolated local development only; no new public demo credentials or admin account are created. Shared demo provisioning belongs to Phase 5 integration.

## Wire conventions and errors

JSON uses snake_case. Timestamps are ISO 8601; depth/distance units are meters except explicit `distance_km`, `radius_km` and casing inches. MD, TVD and TVDSS are distinct; null means unavailable, never zero. Schema requiredness and nullability are separate: a required nullable key is still returned. Input models forbid unknown keys and nonfinite numbers.

Successful documented operations return 200. Common errors: 401 unauthenticated; 403 role/terms/origin denied; 404 resource unavailable; 422 parameter/body/domain validation; 500 unexpected infrastructure failure. HTTP errors use `{"detail":"..."}`; request validation uses `{"detail":[...]}`. Additional endpoint errors are listed below. Error text is diagnostic, not a stable machine code. Login returns 401 for invalid credentials and 429 for rate limiting. Logout needs no authenticated session and returns {"status":"logged_out"}; /auth/me requires a session and returns UserPublic plus linked_identities (array of provider strings). The session cookie is HttpOnly, SameSite=Lax, path=/; Secure follows deployment configuration. No new auth API is introduced.

Paged responses contain `items`, `limit`, `offset`, `has_more`, `as_of`; no total or cursor. Default limit 50, maximum 100, offset 0..10000, except telemetry (default 500, maximum 1000). Unpaged endpoints have no pagination. Generic page `as_of` is response time, not a transactional snapshot. Risk/correlation use active well `as_of` (current time only if absent); telemetry uses window end; query returns its execution context time. `dataset_origin` is on domain records and relevant envelopes, not on every response: terms, probes, auth and audit do not invent it. Seeded domain data says `synthetic_demo`. Depth filter minimum must not exceed maximum; negative depths are allowed only for TVDSS. Channel value_count counts non-null values, including quality-flagged ones; freshness uses good readings.

## Endpoint behavior and ordering

| Endpoint | Auth beyond session + terms | Ordering / behavior / additional errors |
| --- | --- | --- |
| GET /health | Public, no terms | Exact `{ "status":"ok", "service":"sovereign-agentic-workbench-backend" }`; identity retained for existing tests/deployment |
| GET /ready | Public, no terms | 200 ready or 503 not_ready; see probe schema below |
| GET /api/terms; POST /api/terms/accept | Session only | Acceptance idempotent; first acceptance audited |
| GET /api/wells | requester/reviewer/admin | ID ascending |
| GET /api/wells/{well_id} | requester/reviewer/admin | One visible well |
| GET /api/wells/{well_id}/nearby | requester/reviewer/admin | Total score descending, offset ID ascending; all candidates ranked before paging; 100 m scoring window; 422 above 500 candidates |
| GET /api/wells/{well_id}/formations | requester/reviewer/admin | Top MD then interval ID ascending |
| GET /api/wells/{well_id}/correlation | requester/reviewer/admin | Active track first, up to 10 ranked offsets; raw intervals by well/top MD/ID and events by well/MD/ID; 422 above 200 intervals or 500 events |
| GET /api/events | requester/reviewer/admin | Well ID, start MD, event ID ascending; invisible/unknown well filter yields empty list; inclusive MD interval overlap or TVD/TVDSS point filtering |
| GET /api/wells/{well_id}/risk | requester/reviewer/admin | Read-only; 50/100/150 m; calculated assessment IDs are not persisted by GET |
| POST /api/wells/{well_id}/assess | requester/reviewer/admin | No body; persists assessment/evidence, evaluates alert policy, audits; returns only newly emitted advisories (duplicate call can return empty list) |
| GET /api/assessments/{ident} | requester/reviewer/admin | Persisted hazard detail; evidence ordered by event ID; authorizes active and every evidence well |
| GET /api/wells/{well_id}/telemetry | requester/reviewer/admin | Timestamp then channel ascending; bounded window <=24 h; see freshness semantics below |
| POST /api/wells/{well_id}/replay | reviewer/admin | Exact good MD sample timestamp on synthetic active well; invalid seek 422; updates bit depth/as_of and audits |
| POST /api/query | requester/reviewer/admin | Durable four-agent execution; 409 request identity/context conflict; 503 retrieval dependency failure; invalid evidence/filter 422 |
| GET /api/advisories | requester/reviewer/admin | Created time descending, ID ascending; filtered by assessment well scope |
| POST /api/advisories/{ident}/review | reviewer/admin | Pending only; already reviewed 409; records actor/time/reason and audit; no automatic learning |
| GET /api/audit | reviewer/admin | Sequence descending; SIH26121 only; reviewer own actor, admin all |
| POST /api/events/{ident}/validate | reviewer/admin | Uncertain numbers (missing MD or confidence <.5) cannot be validated: 409; corrected source ingestion required; rejection allowed |
| GET /api/reports/{report_id}/source | requester/reviewer/admin | Raw application/pdf, inline; missing report/file 404, hash mismatch 409; append #page=N in browser |
| POST /api/ingest/report | admin | Raw PDF body, NOT multipart; application/pdf required (415), max 20 MiB (413), invalid extraction 422; indexing is separate |

`/ready` returns `{status: "ready"|"not_ready", checks: {fastapi: bool, configuration: bool, postgresql: bool, qdrant: bool, model: bool}, model_check: string}`. It checks runtime/model presence without inference. PostgreSQL readiness is SELECT 1, not schema/seed validation. An isolated stack without the configured model runtime can be not_ready while deterministic NWIS endpoints work. Health/probes have no dataset_origin, as_of, pagination or evidence IDs.

## Domain semantics for frontend tracks

Correlation returns raw formation intervals plus aligned tracks, active/offset wells, events, stored casing points, bit depth and look-ahead start/end. It prefers TVDSS, then TVD when active markers and at least one offset support that datum; otherwise MD. Missing markers on the selected axis remain null with `alignment_available=false`; no perfect geological continuity is inferred. Casing points are null when absent; casing diameter alone does not fabricate shoe depths. Confidence and source remain explicit.

Offset scores are deterministic, not LLM output. Geographic, formation, depth, trajectory, program/context, data-quality and total scores are exposed with weights, algorithm version, depth basis and six explanations. Unknown component scores remain null and contribute zero. Default weights are .15/.30/.20/.15/.10/.10 respectively. The seeded nearest offset OFF-01 ranks below more relevant OFF-04/OFF-09.

Risk emits each supported hazard with probability, confidence, trend, supporting wells, factors, event evidence IDs, historical exposure, live anomaly contribution and data quality. Probability is a heuristic similarity-weighted exposure plus bounded persistent-telemetry modifier, not calibrated field probability. `calibrated=false`, `advisory_only=true`; no LLM generates probabilities. Trend is rising for a qualifying anomaly, otherwise unavailable. Missing usable offsets yields null probability. Data quality includes analog_count, offset_quality, evidence_quality, telemetry_available, telemetry_fresh, telemetry_mode, freshness_basis, depth_bases, contradictory_evidence, calibration and missing; telemetry_features is conditional. telemetry_features is null or an object with mean, std, slope (nullable), rate_of_change (nullable), robust_z (nullable), persistence and count. These are explainable window statistics, not a learned classifier.

Telemetry `from`/`to` default to the hour ending at well as_of (or now). Channels are a trimmed, deduplicated CSV list of 1..20 names, each <=50 characters; absent selection discovers known channels (422 above 20). Per-channel summaries cover the whole window independent of pagination. Unknown channels: known=false, unavailable, zero counts, null unit/timestamps. Known channels with no valid values remain unavailable. Freshness is measured against window end, not wall clock; good finite samples older than 300 seconds are stale. Synthetic data is explicitly source_mode=replay. Bad values are not fabricated or filled.

Alerts require probability >=.6, confidence >=.5, >=2 supporting wells and three successive eligible assessments. Clear threshold .4 supplies hysteresis; cooldown 30 minutes. Identity includes well, hazard and 100 m MD bucket. Same/older timestamps do not advance persistence; gaps >5 minutes reset it. Historical exposure is separate from telemetry anomaly contribution. Assessment IDs deduplicate persisted results under a per-well database lock.

Evidence chain: assessment -> RiskEvidence -> event -> well/report -> source page/span. `evidence_ids` are DrillingEvent IDs. `/api/assessments/{ident}` provides current event, event_at_assessment snapshot, current/assessment source hashes and authorized source_url. Old B1 assessments may lack snapshot/hash (null). `evidence_chunk_id` is nullable and currently null for the structured assessment path. Contribution is an evidence share, not a causal probability attribution. Source URLs never reveal local paths.

## Knowledge query and deterministic demo

`POST /api/query` accepts `mode:"nwis_evidence"` (default for backward compatibility). Legacy `/query` remains separate and unchanged. Structured retrieval is the default; hybrid uses local BGE, sparse Qdrant retrieval, RRF and BGE reranking in `nwis_evidence_v1`. Missing hybrid dependencies fail explicitly. Event metadata and citations identify well/report/page/depth/formation; no uncited drilling conclusion is generated. Reindex after ingestion/validation. Four distinct LangGraph nodes perform offset ranking, evidence retrieval, deterministic risk and cited advisory synthesis; current model_route is deterministic-evidence-template.

Example request (use a fresh UUID for a new request; reuse only for identical retry):

```json
{"mode":"nwis_evidence","request_id":"836ad78d-a3c0-4c23-9582-ea98e8576064","well_id":"ACTIVE-01","query":"show stuck-pipe incidents in Tipam between 2400-2700 m TVD","type":"stuck_pipe","depth_basis":"tvd","depth_min":2400,"depth_max":2700,"retrieval":"structured"}
```

Natural `Tipam` covers Tipam A and B; an explicit formation filter is exact canonical matching. Supported comparison wording includes ?compare events in the three most relevant offsets?; `offset_limit` gives a structured override. `top_k` caps evidence, and risk still evaluates relevant offsets. For ?what mitigations worked for mud losses near this active well??, pass `type:"mud_loss"`; the response cites historical outcomes without guaranteeing success. No evidence means an explicit insufficient-evidence response. Injection/direct rig-control requests are refused.

For the complete persisted demo: reviewer accepts terms, reads ACTIVE-01 offsets, replays 2026-09-29T15:58:00Z, 15:59:00Z, 16:00:00Z with an assess call after each, opens hazard assessment IDs and source PDFs, reviews an advisory, then reads own audit. Repeating persisted timestamps is deliberately idempotent.

## Exact parameters and JSON schemas

The following tables capture actual OpenAPI parameters and model constraints. Path parameters are required strings unless shown otherwise. Raw PDF exceptions and probe response shapes are specified above. Empty parameter tables mean no query/path parameters; request bodies are absent unless stated.


### GET `/health`

Parameters: none.

200 response: map<string, string>.

### GET `/ready`

Parameters: none.

200 response: not typed in OpenAPI; use the explicit response description above.

### POST `/auth/login`

Parameters: none.

Request: `application/json`, LoginRequest; required=True.

200 response: UserPublic.

### POST `/auth/logout`

Parameters: none.

200 response: not typed in OpenAPI; use the explicit response description above.

### GET `/auth/me`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| workbench_session | cookie | False | string or null |  |

200 response: not typed in OpenAPI; use the explicit response description above.

### GET `/api/terms`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| workbench_session | cookie | False | string or null |  |

200 response: TermsOut.

### POST `/api/terms/accept`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| workbench_session | cookie | False | string or null |  |

Request: `application/json`, TermsIn; required=True.

200 response: TermsOut.

### GET `/api/wells`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| limit | query | False | integer | default=50; minimum=1; maximum=100 |
| offset | query | False | integer | default=0; minimum=0; maximum=10000 |
| workbench_session | cookie | False | string or null |  |

200 response: Page_WellOut_.

### GET `/api/wells/{well_id}`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| well_id | path | True | string |  |
| workbench_session | cookie | False | string or null |  |

200 response: WellOut.

### GET `/api/wells/{well_id}/nearby`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| well_id | path | True | string |  |
| radius_km | query | False | number | default=10; maximum=100; exclusiveMinimum=0 |
| limit | query | False | integer | default=50; minimum=1; maximum=100 |
| offset | query | False | integer | default=0; minimum=0; maximum=10000 |
| workbench_session | cookie | False | string or null |  |

200 response: Page_MatchOut_.

### GET `/api/wells/{well_id}/formations`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| well_id | path | True | string |  |
| limit | query | False | integer | default=50; minimum=1; maximum=100 |
| offset | query | False | integer | default=0; minimum=0; maximum=10000 |
| workbench_session | cookie | False | string or null |  |

200 response: Page_FormationOut_.

### GET `/api/reports/{report_id}/source`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| report_id | path | True | string |  |
| workbench_session | cookie | False | string or null |  |

200 response: not typed in OpenAPI; use the explicit response description above.
Actual 200 response: PDF bytes; OpenAPI does not describe this binary response.

### GET `/api/events`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| well_id | query | False | string or null |  |
| formation | query | False | string or null |  |
| type | query | False | enum ["mud_loss", "stuck_pipe", "kick_or_overpressure", "torque_drag", "cementing_issue", "fishing", "npt"] or null |  |
| depth_min | query | False | number or null |  |
| depth_max | query | False | number or null |  |
| depth_basis | query | False | enum ["md", "tvd", "tvdss"] | default="md" |
| limit | query | False | integer | default=50; minimum=1; maximum=100 |
| offset | query | False | integer | default=0; minimum=0; maximum=10000 |
| workbench_session | cookie | False | string or null |  |

200 response: Page_EventOut_.

### GET `/api/wells/{well_id}/correlation`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| well_id | path | True | string |  |
| radius_km | query | False | number | default=10; maximum=100; exclusiveMinimum=0 |
| lookahead_m | query | False | integer | default=100; minimum=50; maximum=150; multipleOf=50 |
| workbench_session | cookie | False | string or null |  |

200 response: CorrelationOut.

### GET `/api/wells/{well_id}/risk`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| well_id | path | True | string |  |
| lookahead_m | query | False | integer | default=100; minimum=50; maximum=150; multipleOf=50 |
| radius_km | query | False | number | default=10; maximum=100; exclusiveMinimum=0 |
| workbench_session | cookie | False | string or null |  |

200 response: RiskOut.

### POST `/api/wells/{well_id}/assess`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| well_id | path | True | string |  |
| lookahead_m | query | False | integer | default=100; minimum=50; maximum=150; multipleOf=50 |
| radius_km | query | False | number | default=10; maximum=100; exclusiveMinimum=0 |
| workbench_session | cookie | False | string or null |  |

200 response: AssessmentOut.

### GET `/api/wells/{well_id}/telemetry`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| well_id | path | True | string |  |
| channels | query | False | string or null |  |
| from | query | False | string (date-time) or null |  |
| to | query | False | string (date-time) or null |  |
| limit | query | False | integer | default=500; minimum=1; maximum=1000 |
| offset | query | False | integer | default=0; minimum=0; maximum=10000 |
| workbench_session | cookie | False | string or null |  |

200 response: TelemetryPage.

### POST `/api/wells/{well_id}/replay`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| well_id | path | True | string |  |
| workbench_session | cookie | False | string or null |  |

Request: `application/json`, ReplayIn; required=True.

200 response: WellOut.

### POST `/api/query`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| workbench_session | cookie | False | string or null |  |

Request: `application/json`, QueryIn; required=True.

200 response: QueryOut.

### GET `/api/assessments/{ident}`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| ident | path | True | string |  |
| workbench_session | cookie | False | string or null |  |

200 response: AssessmentDetail.

### GET `/api/advisories`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| limit | query | False | integer | default=50; minimum=1; maximum=100 |
| offset | query | False | integer | default=0; minimum=0; maximum=10000 |
| workbench_session | cookie | False | string or null |  |

200 response: Page_AdvisoryOut_.

### POST `/api/advisories/{ident}/review`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| ident | path | True | string |  |
| workbench_session | cookie | False | string or null |  |

Request: `application/json`, ReviewIn; required=True.

200 response: AdvisoryOut.

### GET `/api/audit`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| limit | query | False | integer | default=50; minimum=1; maximum=100 |
| offset | query | False | integer | default=0; minimum=0; maximum=10000 |
| workbench_session | cookie | False | string or null |  |

200 response: Page_AuditEventResponse_.

### POST `/api/events/{ident}/validate`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| ident | path | True | string |  |
| workbench_session | cookie | False | string or null |  |

Request: `application/json`, ValidationIn; required=True.

200 response: EventOut.

### POST `/api/ingest/report`

| Parameter | Location | Required | Type | Constraints/default |
| --- | --- | --- | --- | --- |
| well_id | query | True | string |  |
| type | query | True | enum ["WCR", "DDR", "incident", "program"] |  |
| dataset_origin | query | True | string | minLength=1; maxLength=100 |
| workbench_session | cookie | False | string or null |  |

Request: required raw application/pdf bytes (not represented by a JSON model).

200 response: IngestOut.

### Schema `AdvisoryOut`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| id | True | string |  |
| assessment_id | True | string |  |
| text | True | string |  |
| status | True | string |  |
| reviewer | True | string (uuid) or null |  |
| reviewed_at | True | string (date-time) or null |  |
| feedback | True | string or null |  |
| model_route | True | string |  |
| dataset_origin | True | string |  |
| created_at | True | string (date-time) |  |

### Schema `AlignedFormation`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| interval_id | True | string |  |
| formation | True | string |  |
| top | True | number or null |  |
| base | True | number or null |  |
| confidence | True | number |  |
| source | True | string |  |
| alignment_available | True | boolean |  |

### Schema `AssessmentDetail`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| assessment_id | True | string |  |
| well_id | True | string |  |
| as_of | True | string (date-time) |  |
| current_md_m | True | number or null |  |
| formation | True | string or null |  |
| lookahead_m | True | integer |  |
| model_version | True | string |  |
| dataset_origin | True | string |  |
| hazard | True | HazardOut |  |
| evidence | True | array<RiskEvidenceOut> |  |

### Schema `AssessmentOut`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| risk | True | RiskOut |  |
| advisories | True | array<AdvisoryOut> |  |

### Schema `AuditEventResponse`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| id | True | string (uuid) |  |
| chain_id | True | string |  |
| sequence_number | True | integer |  |
| occurred_at | True | string (date-time) |  |
| actor_id | True | string (uuid) or null |  |
| actor_kind | True | string |  |
| event_type | True | string |  |
| request_id | True | string (uuid) or null |  |
| action_revision_id | True | string (uuid) or null |  |
| decision_id | True | string (uuid) or null |  |
| payload | True | object |  |
| canonical_payload_hash | True | string |  |
| payload_redacted | False | boolean | default=true |
| previous_hash | True | string |  |
| event_hash | True | string |  |

### Schema `CasingPoint`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| md | True | number | minimum=0.0 |
| tvd | False | number or null |  |
| tvdss | False | number or null |  |
| size_in | False | number or null |  |
| source | True | string |  |
| confidence | False | number or null |  |

### Schema `ChannelState`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| channel | True | string |  |
| known | True | boolean |  |
| unit | True | string or null |  |
| sample_count | True | integer |  |
| value_count | True | integer |  |
| latest_timestamp | True | string (date-time) or null |  |
| latest_valid_timestamp | True | string (date-time) or null |  |
| state | True | enum ["fresh", "stale", "unavailable"] |  |

### Schema `CorrelationOut`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| well_id | True | string |  |
| as_of | True | string (date-time) |  |
| dataset_origin | True | string |  |
| formations | True | array<FormationOut> |  |
| offset_formations | True | array<FormationOut> |  |
| events | True | array<EventOut> |  |
| offsets | True | array<MatchOut> |  |
| alignment_basis | True | enum ["md", "tvd", "tvdss"] |  |
| current_bit_depth | True | DepthValues |  |
| lookahead_window | True | DepthWindow |  |
| tracks | True | array<CorrelationTrack> |  |
| warning | False | string | default="Formation analogs do not establish geological continuity. Missing datums remain unavailable." |

### Schema `CorrelationTrack`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| well | True | WellOut |  |
| is_active | True | boolean |  |
| formations | True | array<AlignedFormation> |  |
| events | True | array<EventOut> |  |
| casing_points | True | array<CasingPoint> or null |  |

### Schema `DepthValues`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| md | True | number or null |  |
| tvd | True | number or null |  |
| tvdss | True | number or null |  |

### Schema `DepthWindow`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| lookahead_m | True | integer |  |
| start | True | DepthValues |  |
| end | True | DepthValues |  |

### Schema `EventOut`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| id | True | string |  |
| well_id | True | string |  |
| event_type | True | string |  |
| start_depth_md | True | number or null |  |
| end_depth_md | True | number or null |  |
| tvd | True | number or null |  |
| tvdss | True | number or null |  |
| formation | True | string or null |  |
| severity | True | string |  |
| observation | True | string |  |
| cause | True | string or null |  |
| mitigation | True | string or null |  |
| outcome | True | string or null |  |
| npt_hours | True | number or null |  |
| confidence | True | number |  |
| source_report_id | True | string |  |
| source_page | True | integer |  |
| source_span | True | object or null |  |
| raw_phrase | True | string |  |
| verification_state | True | string |  |
| dataset_origin | True | string |  |

### Schema `FormationOut`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| id | True | string |  |
| well_id | True | string |  |
| formation | True | string |  |
| top_md | True | number |  |
| bottom_md | True | number |  |
| top_tvd | True | number or null |  |
| bottom_tvd | True | number or null |  |
| top_tvdss | True | number or null |  |
| bottom_tvdss | True | number or null |  |
| confidence | True | number |  |
| source | True | string |  |
| dataset_origin | True | string |  |

### Schema `HazardOut`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| type | True | enum ["mud_loss", "stuck_pipe", "kick_or_overpressure", "torque_drag", "cementing_issue", "fishing", "npt"] |  |
| assessment_id | True | string |  |
| probability | True | number or null |  |
| confidence | True | number |  |
| trend | True | string |  |
| historical_exposure | True | number or null |  |
| live_anomaly_contribution | True | number or null |  |
| supporting_offset_wells | True | array<string> |  |
| top_factors | True | array<string> |  |
| evidence_ids | True | array<string> |  |
| data_quality | True | object |  |

### Schema `IngestOut`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| report_id | True | string |  |
| status | True | string |  |
| events | True | array<EventOut> |  |
| warnings | True | array<string> |  |
| dataset_origin | True | string |  |

### Schema `LoginRequest`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| username | True | string | minLength=1; maxLength=254 |
| password | True | string | minLength=1; maxLength=255 |

### Schema `MatchOut`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| offset_well_id | True | string |  |
| distance_m | True | number |  |
| distance_km | True | number |  |
| geographic_score | True | number |  |
| formation_score | True | number or null |  |
| depth_score | True | number or null |  |
| trajectory_score | True | number or null |  |
| program_score | True | number or null |  |
| data_quality_score | True | number |  |
| total_score | True | number |  |
| depth_basis | True | string |  |
| weights | True | map<string, number> |  |
| algorithm_version | True | string |  |
| dataset_origin | True | string |  |
| explanation | False | array<string> | default=[] |

### Schema `Page_AdvisoryOut_`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| items | True | array<AdvisoryOut> |  |
| limit | True | integer |  |
| offset | True | integer |  |
| has_more | True | boolean |  |
| as_of | True | string (date-time) |  |

### Schema `Page_AuditEventResponse_`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| items | True | array<AuditEventResponse> |  |
| limit | True | integer |  |
| offset | True | integer |  |
| has_more | True | boolean |  |
| as_of | True | string (date-time) |  |

### Schema `Page_EventOut_`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| items | True | array<EventOut> |  |
| limit | True | integer |  |
| offset | True | integer |  |
| has_more | True | boolean |  |
| as_of | True | string (date-time) |  |

### Schema `Page_FormationOut_`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| items | True | array<FormationOut> |  |
| limit | True | integer |  |
| offset | True | integer |  |
| has_more | True | boolean |  |
| as_of | True | string (date-time) |  |

### Schema `Page_MatchOut_`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| items | True | array<MatchOut> |  |
| limit | True | integer |  |
| offset | True | integer |  |
| has_more | True | boolean |  |
| as_of | True | string (date-time) |  |

### Schema `Page_WellOut_`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| items | True | array<WellOut> |  |
| limit | True | integer |  |
| offset | True | integer |  |
| has_more | True | boolean |  |
| as_of | True | string (date-time) |  |

### Schema `QueryIn`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| mode | False | literal "nwis_evidence" | default="nwis_evidence" |
| offset_limit | False | integer or null |  |
| query | True | string | minLength=1; maxLength=2000 |
| well_id | False | string | default="ACTIVE-01"; minLength=1; maxLength=80 |
| formation | False | string or null |  |
| type | False | enum ["mud_loss", "stuck_pipe", "kick_or_overpressure", "torque_drag", "cementing_issue", "fishing", "npt"] or null |  |
| depth_min | False | number or null |  |
| depth_max | False | number or null |  |
| depth_basis | False | enum ["md", "tvd", "tvdss"] | default="tvd" |
| lookahead_m | False | enum [50, 100, 150] | default=100 |
| radius_km | False | number | default=10; maximum=100.0; exclusiveMinimum=0.0 |
| top_k | False | integer | default=6; minimum=1.0; maximum=20.0 |
| retrieval | False | enum ["structured", "hybrid"] | default="structured" |
| request_id | True | string (uuid) |  |

### Schema `QueryOut`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| mode | False | literal "nwis_evidence" | default="nwis_evidence" |
| execution_id | True | string (uuid) |  |
| status | True | string |  |
| answer | True | string |  |
| evidence | True | array<EventOut> |  |
| offsets | True | array<MatchOut> |  |
| risk | True | RiskOut or null |  |
| warnings | True | array<string> |  |
| model_route | True | string |  |
| as_of | True | string (date-time) |  |
| dataset_origin | True | string |  |

### Schema `ReplayIn`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| as_of | True | string (date-time) |  |

### Schema `ReviewIn`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| status | True | enum ["acknowledged", "dismissed", "reviewed"] |  |
| reason | True | string | minLength=5; maxLength=1000 |

### Schema `RiskEvidenceOut`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| event | True | EventOut |  |
| event_at_assessment | True | EventOut or null |  |
| evidence_chunk_id | True | string or null |  |
| contribution | True | number |  |
| reason | True | string |  |
| source_sha256 | True | string |  |
| source_sha256_at_assessment | True | string or null |  |
| source_url | True | string |  |

### Schema `RiskOut`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| well_id | True | string |  |
| as_of | True | string (date-time) |  |
| current_md_m | True | number or null |  |
| current_tvd_m | True | number or null |  |
| formation | True | string or null |  |
| lookahead_m | True | integer |  |
| hazards | True | array<HazardOut> |  |
| dataset_origin | True | string |  |
| model_version | True | string |  |
| calibrated | False | boolean | default=false |
| advisory_only | False | boolean | default=true |

### Schema `TelemetryOut`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| well_id | True | string |  |
| timestamp | True | string (date-time) |  |
| channel | True | string |  |
| md | True | number |  |
| tvd | True | number or null |  |
| value | True | number or null |  |
| unit | True | string |  |
| quality | True | string |  |
| dataset_origin | True | string |  |

### Schema `TelemetryPage`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| items | True | array<TelemetryOut> |  |
| limit | True | integer |  |
| offset | True | integer |  |
| has_more | True | boolean |  |
| as_of | True | string (date-time) |  |
| dataset_origin | True | string |  |
| source_mode | True | enum ["replay", "historical"] |  |
| window_start | True | string (date-time) |  |
| window_end | True | string (date-time) |  |
| freshness_reference | True | string (date-time) |  |
| stale_after_seconds | False | integer | default=300 |
| channels | True | array<ChannelState> |  |

### Schema `TermsIn`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| version | True | literal "nwis-advisory-v1" |  |
| accepted | True | literal true |  |

### Schema `TermsOut`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| version | False | string | default="nwis-advisory-v1" |
| text | False | string | default="NWIS is an advisory prototype. Synthetic data is not Oil India data. Estimates are uncalibrated; engineering review is required. No rig control is provided." |
| accepted | True | boolean |  |

### Schema `UserPublic`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| id | True | string (uuid) |  |
| username | True | string |  |
| role | True | string |  |
| display_name | False | string or null |  |
| email | False | string or null |  |
| email_verified_at | False | string (date-time) or null |  |
| is_active | False | boolean | default=true |
| signup_pending | False | boolean | default=false |

### Schema `ValidationIn`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| status | True | enum ["validated", "rejected"] |  |
| reason | True | string | minLength=5; maxLength=1000 |

### Schema `WellOut`

| Field | Required | Type (null explicit) | Constraints/default |
| --- | --- | --- | --- |
| id | True | string |  |
| name | True | string |  |
| field | True | string |  |
| latitude | True | number or null |  |
| longitude | True | number or null |  |
| operator | True | string or null |  |
| status | True | string |  |
| spud_date | True | string (date) or null |  |
| total_depth_md | True | number or null |  |
| current_md | True | number or null |  |
| as_of | True | string (date-time) or null |  |
| dataset_origin | True | string |  |

## Prototype limits

Synthetic demo data only; not deployed at Oil India; no live eRTMAC integration. WITSML/ETP-ready adapter boundary only, no full transport or OSDU platform. No automatic drilling control. Risk requires real OIL validation/calibration before operational use. Extraction is conservative explicit-field parsing with source/OCR review, not general trained drilling NLP. Active-formation risk does not forecast multi-formation transitions. Public/shared demo identity provisioning and frontend comparison remain integration work. See [validation](validation.md) for executed checks, not inferred runtime claims.
