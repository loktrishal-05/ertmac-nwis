# eRTMAC-NWIS frontend ↔ backend contract (frontend expectations)

Status: **frontend built; backend integration pending** (Codex NWIS backend worktree).
Source of truth for scope: `docs/eRTMAC_NWIS_Master_Report_SIH26121.pdf` §§16–28, 63, Appendix A.

All calls go through `frontend/src/services/api.js` (`apiRequest`) to the same-origin `/api` prefix.
The Vite dev/preview proxy strips `/api`, so the backend serves these paths at its root.
Path builders live in `frontend/src/features/nwis/nwisModel.js` (`paths`).

Rules the UI relies on:

- Missing values are `null` (never a fake `0`). Non-numeric scores are shown as unknown.
- Lists may be a bare array or `{ items, total }`.
- Every synthetic record carries `dataset_origin: "synthetic_demo"`; the UI shows a "Synthetic demo dataset" badge when present.
- The backend owns distances, similarity scores, probabilities and freshness. The browser never computes radius membership or ranking.

| Screen | Request | Fields read |
|---|---|---|
| Shell context | `GET /wells?limit=200[&q=&status=]` | `id, name, field, lat, lon, status ('drilling' = active), role ('active'), well_type, trajectory_type, spud_date, td_md_m, td_tvd_m, data_quality, current_md_m, current_tvd_m, current_tvdss_m, current_formation, hole_section, formations[{name, top, base, confidence, interpreted}], dataset_origin` |
| Well cockpit | `GET /wells/{id}` | the above plus `trajectory_summary, upcoming_formations[{name, top_tvd_m, distance_m, confidence}], note` |
| Map, offset analysis, dashboard | `GET /wells/{id}/nearby?radius_km=&formation=&hazard=&well_type=&trajectory_type=&min_quality=` | `items[{well, distance_km, total_score, rank, components{geographic, formation, depth, trajectory, program, data_quality}, event_counts{type: n}, formation_at_depth, note}], weights{…}, formula, as_of` — backend order is the ranking |
| Correlation | `GET /wells/{id}/correlation?offsets=A,B&lookahead_m=&depth_ref=tvd` | `depth_ref, current_depth_m, lookahead_m, lookahead_window{top, base}, tracks[{well_id, name, role, td_tvd_m, formations[…], casing[{size, depth}], events[{id, type, depth, severity, confidence, verification, summary}]}]` |
| Events | `GET /events?limit=&well_id=a,b&formation=&type=&severity=&depth_min=&depth_max=&ids=` | `items[{id, well_id, type, raw_observation, depth_md_m, depth_tvd_m, formation, severity, npt_hours, mitigation, outcome, confidence, verification, source{report_id, report_type, page, title}}], total` |
| Risk look-ahead | `GET /wells/{id}/risk?lookahead_m=50\|100\|150` | `as_of, current_md_m, formation, lookahead_m, window_md_m{top, base}, model_version, hazards[{type, probability, confidence, trend, severity?, trend_series[{md_m, probability}], supporting_offset_wells, top_factors, evidence_ids, evidence_count, historical_contribution, telemetry_contribution, data_freshness_s, telemetry_features[], missing_evidence[], confidence_explanation, advisory_id}], evidence[event records]` |
| Live drilling | `GET /wells/{id}/telemetry?window_s=` | `mode ('replay'\|'live'), source, adapter, as_of, stale_after_s, channels[{mnemonic, label, unit, quality}], samples[{t, md_m, values{MNEMONIC: number\|null}}]` — channels without values are listed, never drawn |
| Knowledge search | `POST /query {query, well_id?, mode: 'nwis_evidence', request_id}` | `results[{kind: well\|event\|report, title, excerpt, well_id, event_id?, report_id?, page?, depth_tvd_m?, depth_md_m?, formation?, confidence?, verification?, source?, mitigation?}], summary?, citations?` |
| Advisories | `GET /advisories?well_id=&status=` | `items[{id, well_id, hazard, status, severity, probability, confidence, lookahead_m, interval_md_m{top, base}, formation, created_at, evidence_ids, summary, historical_response[], model_route, reviews[{reviewer, at, decision, feedback, note}]}]` |
| Advisory review | `POST /advisories/{id}/review {decision: acknowledge\|review\|insufficient_evidence\|note, feedback, note}` | returns the updated advisory; reviewer identity comes from the server session; must append `alert_acknowledged` / `advisory_reviewed` audit events |
| Audit | `GET /audit/log?limit=100`, `GET /audit/verify` (existing) | `event_type` (NWIS types: report_ingested, event_extracted, event_validated, offset_query, risk_assessment, alert_created, alert_acknowledged, advisory_reviewed), `sequence_number, occurred_at, actor_id, actor_kind, details` — keys ending in path/file/secret/token/password/credential/hash/key and filesystem-path values are hidden |

Open integration dependencies:

1. `GET /health` must keep returning `service: "sovereign-agentic-workbench-backend"` or `services/api.js#getBackendHealth` must be updated together with a renamed service.
2. `POST /query` currently hosts the legacy governed-query route. NWIS evidence search sends `mode: "nwis_evidence"`; the backend must route it or expose a dedicated path (then change `paths.query`).
3. Demo account: the UI uses existing session auth only. No demo credentials are shipped or invented. `/app/audit` stays restricted to `reviewer`/`admin`; the judge demo account needs a reviewer-capable role or an audit view scoped to its own events.
4. Analyst pin/exclude/compare are session-only view preferences until the backend accepts offset overrides.
