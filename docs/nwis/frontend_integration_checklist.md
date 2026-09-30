# eRTMAC-NWIS frontend integration checklist (B2)

Backend: `pivot/nwis-backend` `a9949c5`, Docker Compose project `ertmac-nwis-backend` (`infra/docker-compose.nwis.yml`), API on `127.0.0.1:8011`.
Contract: `frontend_api_contract.md`. Fixtures: `frontend_fixtures.md` (dev only; must be OFF for everything below).

## 0. Preconditions

- [ ] Backend healthy: `curl http://127.0.0.1:8011/health`.
- [ ] Frontend dev server **without** fixtures, on an origin the backend's same-origin guard allows (default `:5173` or `:3000`):
      `cd frontend && WORKBENCH_API_PROXY=http://127.0.0.1:8011 npx vite --port 3000`. No DEV FIXTURE banner.
- [ ] `npm run lint && npm test && npm run build && npm run verify:dist` green.
- [ ] `NWIS_API_URL=http://127.0.0.1:8011 NWIS_SESSION_COOKIE=… npm run contract:check` → all PASS (the assessment check SKIPs until one is recorded).

## 1. Roles

| Capability | Minimum role |
|---|---|
| All NWIS read screens, knowledge search, "Record assessment" | `requester` (after accepting the terms) |
| Advisory review, telemetry replay seek | `reviewer` |
| Audit screen (`/app/audit`, own entries for non-admins) | `reviewer` |
| Report ingestion, administration | `admin` |

Local demo identities come from the backend's `scripts/seed_dev_users.py` (`dev_requester`, `dev_reviewer`). They are local-only; never use them outside a development machine.

## 2. Golden-demo preparation (backend runbook step 4)

Advisories are raised only after successive assessments. As `dev_reviewer`: `POST /api/wells/ACTIVE-01/replay {"as_of":"2026-09-29T15:58:00Z"}`, then
`POST /api/wells/ACTIVE-01/assess?lookahead_m=100`; repeat for `15:59:00Z` and `16:00:00Z`. The third assessment yields pending advisories
(stuck pipe, mud loss). Re-running on the same timestamps is idempotent.

## 3. Golden flow (fixtures OFF, real backend)

| # | Step | Check |
|---|---|---|
| 1 | Sign in | `/login` → `/app/dashboard`; a user who has not accepted the terms sees the backend terms text and **Accept and continue** before any NWIS data request |
| 2 | Dashboard | ACTIVE-01 MD 2,450 m · TVD 2,450 m · TIPAM_A (from the risk response); hazard cards labelled *uncalibrated estimate*; offsets; alerts; events matrix |
| 3 | Map, radius | 2/5/10/20 km → new `nearby` request; the callout shows OFF-01 as closest (0.1 km) while OFF-04 ranks first; marker event counts come from `/api/events` |
| 4 | Offset ranking | order = backend order; six component scores, weights, depth basis and the backend explanation lines |
| 5 | Correlation | TVD alignment basis, continuity warning, top 3 offsets (or the compare selection) |
| 6 | Events | type/formation/depth-basis/range filters reach `/api/events`; source link opens `/api/reports/{id}/source#page=N` |
| 7 | Risk 100 m | stuck pipe 75 % (0.746), confidence 0.855, rising, historical 0.70 + live anomaly +0.15; *Uncalibrated estimate* badge; replay timestamp |
| 8 | Why this alert? | loads `/api/assessments/{id}`: supporting wells with scores, cited events with report/page links, contribution, source-hash status, telemetry features, missing evidence, confidence basis. On 404: **Record assessment** |
| 9 | Telemetry | SIMULATED / REPLAY banner; channel states from the backend at the replay time |
| 10 | Knowledge | example question → cited answer, grouped wells/events/reports (status `completed`); `refused` shown as refused |
| 11 | Advisory | select the stuck-pipe advisory; hazard/probability/evidence come from its assessment; acknowledge with a reason ≥ 5 chars → status Acknowledged with reviewer and time |
| 12 | Audit | `Advisory reviewed` entry with status and reason; chain verification valid |

## 4. Failure behaviour

- [ ] Backend stopped → every NWIS screen shows "NWIS backend unavailable for …" with Retry; nothing falls back to fixtures.
- [ ] Historical well as context → risk shows "Insufficient evidence / No usable analogs", telemetry "No channels with values".
- [ ] Missing numbers render as `—` / "unknown" / "not recorded", never `0`.
- [ ] Unknown well or assessment → "Not available".

## 5. Known limits (not blockers)

1. B2 has no advisory status/hazard filter or event multi-well filter: the frontend filters one bounded page (≤ 100) and flags `has_more`.
2. The frontend has no replay control; replay is a reviewer data operation (step 2).
3. Analyst pin/compare/exclude are session view preferences; B2 does not accept overrides.
