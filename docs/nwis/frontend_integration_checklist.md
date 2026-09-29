# eRTMAC-NWIS frontend integration checklist

Use when the Codex NWIS backend (`pivot/nwis-backend`) reports ready. Contract: `frontend_api_contract.md`.
Fixtures: `frontend_fixtures.md` (dev only; must be OFF for everything below).

## 0. Preconditions

- [ ] Backend running (default `http://127.0.0.1:8000`, override with `WORKBENCH_API_PROXY` for the Vite proxy).
- [ ] Frontend started **without** fixtures: `cd frontend && npx vite` (no `VITE_NWIS_FIXTURES`). The shell must **not**
      show the DEV FIXTURES pill/banner.
- [ ] `npm run contract:check` with `NWIS_API_URL` and `NWIS_SESSION_COOKIE` → all PASS. Any FAIL lists the exact field;
      fix it in the backend, or add an alias in `frontend/src/features/nwis/adapters.js` (one place), then re-run
      `npm test` (the contract tests pin the adapters).
- [ ] `npm run lint && npm test && npm run build && npm run verify:dist` green.

## 1. Roles (frontend guards; the backend authorizes every request)

| Capability | Minimum role | Enforced by |
|---|---|---|
| Dashboard, wells, map, active well, offset analysis, correlation, events, risk, live, knowledge, help | any signed-in role (`requester` / viewer) | session guard on `/app/*` |
| View advisories | any signed-in role | backend |
| Acknowledge / review / insufficient evidence / note | drilling engineer or `reviewer` (backend decides; UI shows 403 as "Your role cannot review advisories") | backend |
| Audit (`/app/audit`) | `reviewer` or `admin` | frontend route guard + backend |
| Administration | `admin` | frontend route guard + backend |

Judge demo account: needs a role that can **review advisories** and **read audit** (i.e. `reviewer` today, or an NWIS
"drilling engineer" role mapped to the same permissions). No credentials are invented or shipped; RBAC is not weakened.

## 2. Judge flow (fixtures OFF, real backend)

| # | Step | Check |
|---|---|---|
| 1 | Login | `/login` → sign in → lands on `/app/dashboard`; logged-out `/app/*` redirects to `/login?next=…` |
| 2 | Dashboard | active well MD/TVD/formation/section; 4 hazard cards; offset coverage; mini-map; alerts; data quality; events matrix; synthetic badge only if `dataset_origin=synthetic_demo` |
| 3 | Well list | `/app/wells` lists catalogue; search and status filter hit the server (`q`, `status`) |
| 4 | Active well | `/app/active` → `/app/wells/{id}`; telemetry strip shows only channels with values; offset well pages show stratigraphy/events, risk 404 → "Not available" |
| 5 | Radius change | map 2/5/10/20 km → new `nearby` request; ring redraws; markers = backend items; table matches |
| 6 | Offset ranking | `/app/offset-analysis` order = backend order; component scores + weights shown; closest-well callout appears when the closest well is not #1 |
| 7 | Correlation | tracks on TVD; formation bands, interpreted hatching, unknown tops "?", events clickable, casing, look-ahead band |
| 8 | Events | filters (well, formation, type, severity, TVD range) map to query params; source wording + report/page shown |
| 9 | Risk 50/100/150 m | segmented control changes `lookahead_m`; profile table shows all three; no overall risk number |
| 10 | Why this alert? | drawer lists supporting wells with scores, cited events (report + page), telemetry features, missing evidence, confidence explanation |
| 11 | Telemetry replay | `/app/live` banner says SIMULATED / REPLAY unless `mode=live`; stale data flagged; refresh every 15 s |
| 12 | Knowledge query | example query → results grouped Wells / Events / Reports with citations; a legacy response shows "Unrecognised search response" |
| 13 | Advisory acknowledgement | note required; decision recorded; list status updates; 403/409/422 shown inline |
| 14 | Audit event | `/app/audit` shows `Alert acknowledged` / `Advisory reviewed` for step 13; chain verification shown |

## 3. Failure behaviour (must hold with the real backend)

- [ ] Stop the backend → every NWIS screen shows "NWIS backend unavailable for …" with Retry; nothing falls back to fixtures.
- [ ] A 404 for risk/telemetry on an offset well → "Not available", not an error wall.
- [ ] Missing numbers render as `—` / "unknown" / "not reported", never `0`.
- [ ] MapLibre chunk loads only on `/app/map` and the dashboard mini-map; no external tile or font requests.

## 4. Known dependencies to resolve with Codex

1. `POST /query` must answer `mode: "nwis_evidence"` with `results` (or provide a dedicated path).
2. Audit writes for `alert_acknowledged` / `advisory_reviewed` on review.
3. Demo account role (section 1).
