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

| Path | Fixture content |
|---|---|
| `/auth/me` | Dev-only session `fixture-engineer` (role `reviewer`). **Not a credential**: no password exists, and login is not faked. |
| `/wells`, `/wells/{id}` | `ACTIVE-01` (drilling, MD 2,450 m / TVD 2,382 m, TIPAM_A) and offsets `OFF-01`…`OFF-13` in "NWIS Demo Field (synthetic)". Positions are arbitrary synthetic coordinates. |
| `/wells/ACTIVE-01/nearby` | Radius-filtered offsets with six hand-authored component scores and weights. The story: `OFF-02` is closest (1.1 km, across a fault) but ranks low; `OFF-04`/`OFF-09` rank first. `OFF-12` is close but never reached the interval. |
| `/wells/ACTIVE-01/correlation` | TVD tracks with five formations (NAMSANG, GIRUJAN, TIPAM_A, TIPAM_B, BARAIL), interpreted/unknown intervals, casing shoes and events. |
| `/events` | 27 events across 10 hazard types with source wording, mitigation, outcome, NPT, confidence, verification and report/page citations. |
| `/wells/ACTIVE-01/risk` | Four hazards per look-ahead window (50/100/150 m) with trend series, supporting wells, evidence IDs, telemetry features, missing evidence and a confidence explanation. |
| `/wells/ACTIVE-01/telemetry` | 120 replay samples anchored to "now" (mode `replay`); torque rises in the last 25 samples. `PIT` is declared but has no values, to exercise the "never draw missing channels" rule. |
| `/query` (POST) | Keyword filter over fixture events (no model call). |
| `/advisories`, `/advisories/{id}/review` | Three advisories. Review requires a valid decision and a note of at least 5 characters, and appends an audit event. |
| `/audit/log`, `/audit/verify` | In-memory NWIS audit events. The verification result is labelled "Fixture chain: not a real tamper-evidence check". |

Nothing in the fixtures is Oil India data. The values mirror the master report's synthetic demo design (§42) and exist only so the
screens can be built and browser-tested before the Codex backend lands.

## Dev fixtures vs schema samples vs production

| | Dev fixtures (`fixtures.js`) | Schema samples (`contractSamples.js`) |
|---|---|---|
| Purpose | click through the UI before the backend exists | contract/render tests (full + sparse/null variants) |
| Loaded by | `services/api.js`, only when `DEV && VITE_NWIS_FIXTURES=1` | tests only |
| In production bundle | never (`npm run verify:dist` fails the check if they appear) | never |

If a production API call fails, the screen shows an unavailable/error state; there is no fixture fallback
(`services/api.test.js` pins the gate and the no-fallback behaviour; `contract.test.js` keeps fixtures in sync with the contract).
