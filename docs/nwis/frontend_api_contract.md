# eRTMAC-NWIS frontend ↔ backend contract (B2)

Status: **integrated** with backend `pivot/nwis-backend` at `a9949c5` (B2). This documents only what the frontend consumes.
Backend schemas: `backend/app/schemas/nwis.py`; backend runbook: `docs/nwis/README.md` in the backend worktree.

Executable form: `frontend/src/features/nwis/contract.js` (`validateContract`). Adapters, the only code that reads raw
field names: `frontend/src/features/nwis/adapters.js`. Check a running backend:

```bash
cd frontend
NWIS_API_URL=http://127.0.0.1:8011 NWIS_SESSION_COOKIE='<cookie header from a signed-in session>' npm run contract:check
```

## Transport

- All calls go through `services/api.js#apiRequest` with a same-origin `/api` prefix (`credentials: include`, JSON).
- Backend route families: NWIS routes live under `/api` (`/api/wells`, `/api/events`, `/api/query`, `/api/assessments`,
  `/api/advisories`, `/api/terms`, `/api/reports`, `/api/ingest`, `/api/audit`). Shared routes stay at the root
  (`/auth/*`, `/health`, `/audit/verify`).
- The dev/preview proxy (`src/services/apiRoutes.js#rewriteApiPath`, used by `vite.config.js`) keeps `/api` for NWIS families
  and strips it for root routes. Tested in `src/services/apiRoutes.test.js`.
- Browser writes pass the backend same-origin guard only from allowed origins (`http://localhost:5173`, `http://127.0.0.1:5173`,
  `:3000` variants by default).
- **Terms:** every NWIS route returns 403 "Accept NWIS advisory terms first" until `POST /api/terms/accept
  {"version":"nwis-advisory-v1","accepted":true}`. `TermsGate` (in `components.jsx`, mounted in `AppShell`) reads `GET /api/terms`
  and shows the backend's text with an Accept button before any NWIS request is made.

## Conventions

- **Lists** are pages `{ items, limit, offset, has_more, as_of }`; there is no `total`. Limits: wells/nearby/events/formations/advisories/audit ≤ 100,
  telemetry ≤ 1000. When `has_more` is true the UI says the list is partial.
- **Nullability:** `num?` = number or null. The UI shows `—`, "unknown", "not recorded" or "unavailable", **never** 0.
- **`dataset_origin`** `"synthetic_demo"` shows the *Synthetic demo dataset* badge. The frontend never sets it.
- **Time:** replay data is relative to the replay reference time (`as_of` / `freshness_reference`, e.g. `2026-09-29T16:00:00Z`), never to the wall clock.
- **Ordering:** the backend owns the ranking. Nearby items arrive in `total_score` order; the UI never re-ranks.

## Endpoints consumed

| Endpoint | Used by | Notes |
|---|---|---|
| `GET /api/terms`, `POST /api/terms/accept` | TermsGate | `{version, text, accepted}` |
| `GET /api/wells?limit=100` | context, catalogue, map placement | `WellOut{id, name, field, latitude, longitude, operator, status ("ACTIVE"/"historical"), spud_date, total_depth_md, current_md, as_of, dataset_origin}`. No formation/TVD: those come from the risk response. |
| `GET /api/wells/{id}` | well record | `WellOut` |
| `GET /api/wells/{id}/formations?limit=100` | formation tables, event filter | `FormationOut{formation, top_md, bottom_md, top_tvd?, bottom_tvd?, top_tvdss?, bottom_tvdss?, confidence}` |
| `GET /api/wells/{id}/nearby?radius_km=` | map, offset analysis, dashboard | flat `MatchOut{offset_well_id, distance_m, distance_km, geographic/formation/depth/trajectory/program/data_quality_score, total_score, depth_basis, weights, algorithm_version, explanation[]}`. No coordinates (joined from the well list by id) and no event counts (counted from `/api/events`; unknown while loading or if the page is partial). |
| `GET /api/wells/{id}/correlation?lookahead_m=` | correlation | `alignment_basis` (tvdss → tvd → md), `current_bit_depth{md,tvd,tvdss}`, `lookahead_window{lookahead_m,start,end}`, `tracks[{well, is_active, formations[{formation, top, base, confidence, alignment_available}], events: EventOut[], casing_points?}]`, `warning`. The backend chooses the top 10 offsets; the UI filters the returned tracks by the compare selection or shows the top 3. |
| `GET /api/events?…` | events, dashboard, map counts | Filters: `well_id` (single), `formation`, `type` (mud_loss, stuck_pipe, kick_or_overpressure, torque_drag, cementing_issue, fishing, npt), `depth_basis` + `depth_min`/`depth_max`, `limit ≤ 100`. `EventOut{id, well_id, event_type, start_depth_md, end_depth_md, tvd, tvdss, formation, severity, observation, raw_phrase, cause, mitigation, outcome, npt_hours, confidence, source_report_id, source_page, verification_state}` |
| `GET /api/reports/{id}/source#page=N` | source links | PDF |
| `GET /api/wells/{id}/risk?lookahead_m=50\|100\|150` | risk, dashboard, cockpit, context | `{well_id, as_of, current_md_m, current_tvd_m, formation, lookahead_m, model_version, calibrated:false, advisory_only:true, hazards[]}`. Hazard: `{type, assessment_id, probability?, confidence, trend ("rising"/"unavailable"), historical_exposure?, live_anomaly_contribution?, supporting_offset_wells[], top_factors[], evidence_ids[], data_quality{analog_count, offset_quality, evidence_quality, telemetry_available, telemetry_fresh, telemetry_features, telemetry_mode, depth_bases, contradictory_evidence, calibration, missing[]}}`. Any other `lookahead_m` is 422. |
| `POST /api/wells/{id}/assess?lookahead_m=` | "Record assessment" in the evidence drawer | persists the assessment; returns `{risk, advisories[]}` |
| `GET /api/assessments/{id}` | "Why this alert?", advisory detail | `{assessment_id, well_id, as_of, current_md_m, formation, lookahead_m, model_version, hazard, evidence[{event, event_at_assessment?, contribution, reason, source_sha256, source_sha256_at_assessment?, source_url}]}`. 404 until recorded; the drawer then offers "Record assessment". |
| `GET /api/wells/{id}/telemetry?limit=1000` | live, cockpit strip, dashboard | Page of rows `{timestamp, channel, md, tvd?, value?, unit, quality}` plus `source_mode` (replay/historical), `window_start`, `window_end`, `freshness_reference`, `stale_after_seconds`, `channels[{channel, known, unit, value_count, state: fresh\|stale\|unavailable}]`. Only rows with `quality="good"` and a value are drawn. |
| `POST /api/query` | knowledge | Body `{query, request_id (UUID), well_id, mode: "nwis_evidence"}` → `{mode, status ("completed"/"refused"), answer, evidence: EventOut[], warnings[], model_route}`. The frontend groups cited events into wells/events/reports and adds nothing. Any other response shape is shown as unrecognised. |
| `GET /api/advisories?limit=100` | advisories, dashboard alerts | `AdvisoryOut{id, assessment_id, text, status (pending_review/acknowledged/reviewed/dismissed), reviewer?, reviewed_at?, feedback?, model_route, created_at}`. No hazard/well filters; hazard and evidence come from the linked assessment. |
| `POST /api/advisories/{id}/review` | review form | Body `{status: acknowledged\|reviewed\|dismissed, reason (5–1000 chars)}`. Reviewer role; 409 if already reviewed. |
| `GET /api/audit?limit=100`, `GET /audit/verify` | audit | `AuditEventResponse{id, sequence_number, occurred_at, actor_id, actor_kind, event_type, payload{action, product, …}}`. The label comes from `payload.action`. Hashes, paths and secrets are hidden. |

## Error semantics

| Status | Frontend behaviour |
|---|---|
| 401 | Session expired; guarded routes redirect to `/login?next=…`. |
| 403 | "Access restricted" (terms are handled by TermsGate first); review shows "Your role cannot review advisories." |
| 404 | "Not available" state; the evidence drawer offers to record the assessment. |
| 409 | "This advisory was already reviewed" inline. |
| 422 | `detail` shown inline. |
| 5xx, network, timeout | "NWIS backend unavailable for …" with Retry. No fixture or cached fallback in production. |

## Safety wording

Estimates are labelled *uncalibrated* (B2 `calibrated=false`). Replay telemetry is labelled SIMULATED / REPLAY, never live eRTMAC.
Nothing in the UI controls rig equipment. The product is "designed for Oil India / eRTMAC workflows", not deployed there.
