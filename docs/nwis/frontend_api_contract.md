# eRTMAC-NWIS frontend ↔ backend contract

Status: **locked for integration** (frontend `pivot/nwis-frontend`). This documents only what the frontend actually
consumes; it does not prescribe backend implementation. Product authority: `docs/eRTMAC_NWIS_Master_Report_SIH26121.pdf`
(§§16–28, 63, Appendix A).

Executable form: `frontend/src/features/nwis/contract.js` (`validateContract`). Adapters (the only code that reads
raw field names): `frontend/src/features/nwis/adapters.js`. Check a running backend with:

```bash
cd frontend
NWIS_API_URL=http://127.0.0.1:8000 NWIS_SESSION_COOKIE='<cookie header from a signed-in browser>' npm run contract:check
```

## Transport and conventions

- All calls: `services/api.js#apiRequest`, same-origin `/api` prefix, `credentials: include`, `cache: no-store`, JSON.
  The Vite dev/preview proxy strips `/api`; the backend serves the paths below at its root.
- **Nullability:** notation `num?` = number or `null`/absent. The UI shows `—`, "unknown" or "not reported" for null and
  **never** substitutes 0. Absent optional lists are treated as empty.
- **Lists:** either a bare JSON array or an envelope `{ items: [...], total?: num }`. `total` is the full match count;
  when `total > items.length` the UI says "showing N". No cursor pagination is consumed; the frontend sends `limit`.
- **`dataset_origin`:** optional string on envelopes and on records. `"synthetic_demo"` shows a *Synthetic demo dataset*
  badge. The frontend never sets or infers it.
- **`as_of`:** ISO-8601 UTC string. Used for "last sample N ago" (telemetry freshness) and "assessment time" (risk).
- **IDs:** strings (`ACTIVE-01`, `OFF-04`, `EVT-102`, `ADV-0012`). Path segments are URL-encoded.
- **Ordering:** the backend owns ordering. `nearby` items **must** be returned in rank order (the UI shows them as-is).

### Error semantics (all endpoints)

| Status | Frontend behaviour |
|---|---|
| 401 | Dispatches `workbench-session-expired`; guarded routes redirect to `/login?next=…`. `/auth/me` 401 = anonymous. |
| 403 | "Access restricted" state with `detail`; advisory review shows "Your role cannot review advisories." |
| 404 | "Not available" state with `detail` (e.g. risk/telemetry for a well that is not drilling). |
| 409 | "The record changed … refresh" state (used for concurrent advisory review). |
| 422 | `detail` string, or `detail[].msg` joined, shown inline (advisory review validation). |
| 5xx, network, timeout | "NWIS backend unavailable for …" with Retry. **No fixture or cached fallback in production.** |
| 2xx with empty/invalid JSON | Treated as an error ("Backend returned an empty or invalid JSON response"). |

`detail` may be a string or FastAPI-style `[{ msg }]`.

---

## 1. `GET /wells`

Query: `limit` (sent as 200), `q` (free-text id/name filter, optional), `status` (`drilling|completed|suspended|abandoned`, optional).
Response: list of **Well**. Ordering: backend order (displayed as-is).

**Well**

| Field | Type | Notes |
|---|---|---|
| `id` | str | **required** |
| `name` | str? | falls back to `id` |
| `field`, `status`, `role` | str? | `status: "drilling"` or `role: "active"` marks the default active well |
| `lat`, `lon` | num? | WGS-84 surface location; null → map says it cannot be drawn |
| `well_type`, `trajectory_type`, `trajectory_summary`, `spud_date` | str? | |
| `td_md_m`, `td_tvd_m` | num? | |
| `data_quality` | num? | 0–1 |
| `current_md_m`, `current_tvd_m`, `current_tvdss_m` | num? | drilling well only; TVDSS may be null |
| `current_formation`, `hole_section` | str? | |
| `formations` | Formation[]? | `{ name: str, top: num?, base: num?, confidence: num?, interpreted: bool? }` (TVD m) |
| `upcoming_formations` | list? | `{ name, top_tvd_m: num?, distance_m: num?, confidence: num? }` |
| `casing` | list? | `{ size: str?, shoe_tvd_m: num? }` |
| `note` | str? | analyst-facing note (e.g. "across mapped fault") |
| `dataset_origin` | str? | |

## 2. `GET /wells/{id}`

Response: one **Well** (same schema). 404 → "Not available".

## 3. `GET /wells/{id}/nearby`

Query: `radius_km` (2 | 5 | 10 | 20; 20 also used for correlation/risk pickers), optional filters `formation`, `hazard`,
`well_type`, `trajectory_type`, `min_quality` (0.5 | 0.75). **The backend performs the radius query and scoring**; the
browser never computes distance or rank.
Response: envelope with `items` in **rank order**, plus `radius_km: num?`, `weights: {component: num}?`, `formula: str?`,
`as_of: str?`, `dataset_origin: str?`, `total: num?`.

**NearbyWell** item: `well` (Well, `id` required), `distance_km: num?`, `total_score: num?`, `rank: num?` (defaults to
position), `components: { geographic, formation, depth, trajectory, program, data_quality }` (each `num?`, 0–1),
`event_counts: { <event_type>: num }?`, `formation_at_depth: str?`, `note: str?`.
Zero items → "No offset wells within N km".

## 4. `GET /wells/{id}/correlation`

Query: `offsets` (comma-separated well ids, optional; empty → backend picks its top-ranked offsets), `lookahead_m`
(50 | 100 | 150), `depth_ref=tvd`.
Response:

| Field | Type | Notes |
|---|---|---|
| `depth_ref` | str | axis label (`tvd` preferred; `tvdss`/`md` shown as given) |
| `current_depth_m` | num? | active bit depth on the axis |
| `lookahead_m` | num? | |
| `lookahead_window` | `{ top: num, base: num }`? | null → no window drawn |
| `tracks` | list | first `role: "active"` track, then offsets |
| `tracks[].well_id` | str | **required** |
| `tracks[].name`, `role` | str? | |
| `tracks[].td_tvd_m` | num? | below-TD hatching |
| `tracks[].formations` | Formation[] | null top/base → not drawn, "unknown" in table; `interpreted: true` → hatched; `confidence: null` → "?" |
| `tracks[].casing` | list? | `{ size: str?, depth: num? }` |
| `tracks[].events` | list | `{ id: str, type: str, depth: num?, severity: str?, confidence: num?, verification: str?, summary: str? }`; null depth → not drawn |
| `as_of`, `dataset_origin`, `well_id` | str? | |

## 5. `GET /events`

Query: `limit` (100; 500 for dashboard aggregation), optional `well_id` (comma-separated), `formation`, `type`,
`severity` (`low|moderate|high`), `depth_min`, `depth_max` (TVD m), `ids` (comma-separated, for evidence lookups).
Response: list of **DrillingEvent**; `total` drives "N events (showing M)".

**DrillingEvent**: `id: str`, `well_id: str`, `type: str` (normalized taxonomy, report §34), `raw_observation: str?`
(source wording, shown verbatim), `depth_md_m: num?`, `depth_tvd_m: num?`, `formation: str?`, `severity: str?`,
`npt_hours: num?`, `mitigation: str?`, `outcome: str?`, `confidence: num?` (extraction), `verification: str?`
(`verified|needs_review|…`), `source: { report_id: str?, report_type: str?, page: num?, title: str? }?`, `dataset_origin: str?`.

## 6. `GET /wells/{id}/risk`

Query: `lookahead_m` = 50 | 100 | 150 (the Risk page requests all three for the profile table).
404 for a non-drilling well → "Not available".

| Field | Type | Notes |
|---|---|---|
| `as_of` | str | **required** — assessment time |
| `lookahead_m` | num | **required** |
| `window_md_m` | `{ top, base }`? | assessed interval |
| `current_md_m`, `formation`, `model_version`, `well_id`, `dataset_origin` | ? | |
| `hazards` | list | one card per hazard; **no aggregate "overall risk" is read or shown** |
| `evidence` | DrillingEvent[]? | detail records for the ids cited by hazards ("Why this alert?") |

**Hazard**: `type: str` (required), `probability: num?`, `confidence: num?` (separate fields; the LLM supplies neither),
`trend: str?` (`rising|steady|falling`), `severity: str?` (only `"critical"` turns a card red), `trend_series: [{ md_m, probability }]?`,
`supporting_offset_wells: str[]?`, `top_factors: str[]?`, `evidence_ids: str[]?` (references into `evidence` / `/events?ids=`),
`evidence_count: num?` (null + no ids → "Not reported"), `historical_contribution: num?`, `telemetry_contribution: num?`,
`data_freshness_s: num?` (null → "Historical only"), `telemetry_features: str[]?`, `missing_evidence: str[]?`,
`confidence_explanation: str?`, `advisory_id: str?`.

## 7. `GET /wells/{id}/telemetry`

Query: `window_s` (600 dashboard, 1800 cockpit, 7200 live). Polled every 15 s while the Live page is visible.

| Field | Type | Notes |
|---|---|---|
| `mode` | str | **required**; anything other than `"live"` is labelled **SIMULATED / REPLAY DATA** |
| `source`, `adapter` | str? | shown verbatim (e.g. "WITSML / ETP-ready adapter") |
| `as_of` | str? | last sample time → fresh/stale |
| `stale_after_s` | num? | default 120 s |
| `channels` | `[{ mnemonic: str, label?, unit?, quality? }]` | declared channels |
| `samples` | `[{ t: str (ISO), md_m: num?, values: { <MNEMONIC>: num? } }]` | a channel with no numeric values is listed as "declared without values" and never drawn |
| `well_id`, `dataset_origin` | str? | |

## 8. `POST /query` (knowledge evidence search)

Body: `{ query: str (≤1000), well_id?: str, mode: "nwis_evidence", request_id: uuid }`. Timeout 120 s.
Response:

| Field | Type | Notes |
|---|---|---|
| `results` | list | **required** — its absence means "not an NWIS evidence response" (see below) |
| `results[].kind` | `"well" \| "event" \| "report"` | grouping; unknown kinds are shown under Reports |
| `results[].title`, `excerpt`, `well_id`, `event_id`, `report_id`, `formation`, `verification` | str? | |
| `results[].page`, `depth_tvd_m`, `depth_md_m`, `confidence` | num? | `report_id`/`page` may also arrive inside `source` |
| `summary` | str? | shown only as "Cited summary"; if `citations` is empty the UI marks it unsupported |
| `citations` | list? | |
| `mode`, `dataset_origin` | str? | |

**Legacy boundary:** the old SIH26117 governed-query response (`agent_result`, `evidence`, `route` …, no `results`) is
detected by `adaptQuery` and shown as "Unrecognised search response" — it is never parsed as NWIS evidence.

## 9. `GET /advisories`

Query: `well_id` (active well), optional `status` (`open|acknowledged|reviewed|insufficient_evidence`).
Response: list of **Advisory**: `id: str`, `hazard: str`, `status: str` (all required); `well_id`, `severity`, `formation`,
`created_at`, `summary` (NWIS advisory text), `model_route`: str?; `probability`, `confidence`, `lookahead_m`: num?;
`interval_md_m: { top, base }?`; `evidence_ids: str[]?` (resolved via `GET /events?ids=`); `historical_response: str[]?`;
`reviews: [{ reviewer: str?, at: str?, decision: str, feedback: str?, note: str? }]?`; `dataset_origin: str?`.

## 10. `POST /advisories/{id}/review`

Body: `{ decision: "acknowledge" | "review" | "insufficient_evidence" | "note", feedback: "useful" | "already_known" | "false_positive" | "insufficient_evidence", note: str (≥5 chars, ≤2000) }`.
Reviewer identity and timestamp come from the server session, never the body. Response: any 2xx JSON (the frontend
re-fetches the advisory list). Expected: 403 for roles that cannot review, 404 unknown advisory, 409 concurrent change,
422 validation. The backend is expected to append `alert_acknowledged` / `advisory_reviewed` audit events. A review never
changes rig equipment, mud programs or drilling parameters.

## 11. `GET /audit/log` and `GET /audit/verify` (existing chain)

`/audit/log?limit=100` → list of **AuditEvent**: `sequence_number: num`, `event_type: str` (required); `occurred_at`,
`actor_id`, `actor_kind`: str?; `details` (or legacy `payload`): obj?. NWIS event types shown with readable labels:
`report_ingested, event_extracted, event_validated, offset_query, risk_assessment, alert_created, alert_acknowledged,
advisory_reviewed` (case-insensitive). Detail keys ending in path/file/secret/token/password/credential/hash/key and
values that look like filesystem paths are hidden.
`/audit/verify` → `{ valid: bool, events_checked?: num, note?: str }`.

## 12. `GET /health` and `GET /auth/me`

- `/health`: healthy = HTTP 2xx **and** `status` ∈ `ok | healthy | up` (case-insensitive). The `service` name is **not**
  checked, so rebranding the backend to eRTMAC-NWIS is safe.
- `/auth/me`: `{ id, username, role }`; `role` drives navigation guards (see the integration checklist).

## Open integration dependencies

1. `POST /query` hosts the legacy governed route today; the backend must answer `mode: "nwis_evidence"` with `results`
   (or expose a dedicated path — then change `paths.query` in `nwisModel.js`, nothing else).
2. Demo account: a role that can review advisories and read audit (see checklist). No credentials are shipped.
3. Pin / exclude / compare offsets are session-only until the backend accepts analyst overrides.
