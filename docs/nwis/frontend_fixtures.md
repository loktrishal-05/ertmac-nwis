# eRTMAC-NWIS frontend development fixtures

File: `frontend/src/features/nwis/fixtures.js`. Tests: `frontend/src/features/nwis/nwisModel.test.js`.

## When they are active

Only when **both** hold:

1. Vite development mode (`import.meta.env.DEV`), and
2. `VITE_NWIS_FIXTURES=1` is set when starting the dev server:

```bash
cd frontend
VITE_NWIS_FIXTURES=1 npx vite            # PowerShell: $env:VITE_NWIS_FIXTURES='1'; npx vite
```

Vite folds `import.meta.env.DEV` to `false` in `npm run build`, so the fixture module is not bundled
(verified: the production `dist/` contains no fixture strings). Production always calls the real API.

When active, the shell shows a **DEV FIXTURES** pill and a "DEV FIXTURE MODE" banner on every screen,
and every record carries `dataset_origin: "synthetic_demo"`, so the "Synthetic demo dataset" badge is shown too.
Unknown paths (for example `/health`) fall through to the real backend, so backend health stays honest.

## What each fixture provides

Every response uses the B2 shapes in `frontend_api_contract.md`; `contract.test.js` validates the fixtures against the same contract as the live backend.
Replay time is fixed at `2026-09-29T16:00:00Z`, as in the B2 demo seed.

| Path | Fixture content |
|---|---|
| `/auth/me` | Dev-only session `fixture-engineer` (role `reviewer`). **Not a credential**: no password exists, and login is not faked. |
| `/terms`, `/terms/accept` | Terms already accepted. |
| `/wells`, `/wells/{id}`, `/wells/{id}/formations` | `ACTIVE-01` (status `ACTIVE`, MD 2,450 m) and historical offsets `OFF-01`…`OFF-13` with synthetic coordinates and formation tables. |
| `/wells/ACTIVE-01/nearby` | Flat match items with six hand-authored component scores, weights and explanation lines. `OFF-02` is closest but ranks low; `OFF-04`/`OFF-09` rank first. |
| `/wells/ACTIVE-01/correlation` | TVD alignment, top 10 offsets as tracks with formations, events and casing points. |
| `/events` | 27 events over the 7 B2 hazard types with source wording, mitigation, outcome, NPT, confidence, verification and report/page. |
| `/wells/ACTIVE-01/risk`, `/assess`, `/assessments/{id}` | Four hazards per look-ahead (50/100/150 m; other values 422), `calibrated:false`, historical exposure plus a bounded live anomaly, assessment ids `fx-{lookahead}-{hazard}` with evidence links. |
| `/wells/ACTIVE-01/telemetry` | 61 one-minute replay samples per channel before the replay time; torque rises at the end; `pit_volume` is declared but empty (state `unavailable`). |
| `/query` (POST) | Keyword filter over fixture events (no model call), `mode: nwis_evidence`, `status: completed`. |
| `/advisories`, `/advisories/{id}/review` | Three advisories (pending, acknowledged, dismissed). Review requires `{status, reason ≥ 5}`, returns 409 when already reviewed, and appends an audit entry. |
| `/audit`, `/audit/verify` | In-memory entries with `payload.action`. Verification is labelled "Fixture chain: not a real tamper-evidence check". |

Nothing in the fixtures is Oil India data. They exist so screens can be exercised without the backend.

## Dev fixtures vs schema samples vs production

| | Dev fixtures (`fixtures.js`) | Schema samples (`contractSamples.js`) |
|---|---|---|
| Purpose | click through the UI without a running backend | contract/render tests (full + sparse/null variants) |
| Loaded by | `services/api.js`, only when `DEV && VITE_NWIS_FIXTURES=1` | tests only |
| In production bundle | never (`npm run verify:dist` fails the check if they appear) | never |

If a production API call fails, the screen shows an unavailable/error state; there is no fixture fallback
(`services/api.test.js` pins the gate and the no-fallback behaviour; `contract.test.js` keeps fixtures in sync with the contract).
