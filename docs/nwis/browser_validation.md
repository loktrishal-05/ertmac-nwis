# SIH26121 eRTMAC-NWIS F1b browser release verification

2026-09-30. Inspected candidate: `f84abbccc5396c24bda19264e8e1e21c91332740`, clean on `release/nwis-final`. Frontend and backend share this combined release worktree. The final branch HEAD includes the verified CSS/documentation fixes below. Backend files remain byte-identical to application freeze `244b86c082174ceb9703625f70dc7d6851806705`; neither backend tuning nor another held-out evaluation occurred.

## Actual browser and runtime

Connected browser inventory was empty. The explicitly authorized Playwright fallback used installed Chromium 153.0.8010.12, first headless shell, then full Chromium with D3D11 for the final console/network smoke. No browser checks were simulated with server rendering.

The existing isolated `nwis-final-validation` stack was reused. Backend readiness passed FastAPI/configuration/PostgreSQL/Qdrant/model checks. PostgreSQL/PostGIS and Qdrant have no host-published ports. Backend 8014, test inbox 8026 and frontend preview 5173 are loopback only. No production/public exposure, deployment, push or main/master merge occurred.

## Coverage and results

All 20 requested surfaces were exercised in the browser: landing, sign in, sign up, forgot password, OTP request, OTP verification, terms, dashboard, wells, nearby map, offset analysis, correlation, historical events, risk, evidence drawer, replay telemetry, knowledge, advisories, audit and help. Google is disabled and its sign-in button is hidden.

Auth used a disposable requester and the existing limited synthetic-demo reviewer; no admin credentials. Signup and actual SMTP delivery into the isolated Mailpit inbox succeeded. Email verification and password recovery/reset succeeded. Incorrect codes, a reused recovery OTP and an unused recovery OTP after 764 seconds were rejected. New-password sign-in worked. Logout returned to sign in and rejected navigation to the protected dashboard. A fresh account saw the NWIS terms gate; accepting the advisory notice unlocked the application. External SMTP/Google provider configuration was not claimed live-validated by this local phase. The development inbox hint uses the standard local-stack 8025 address; the isolated validation mailbox was inspected on 8026.

The golden browser journey passed: ACTIVE-01; OFF-01 closest (approximately 149 m, rank 11); OFF-04 best analog (rank 1, approximately 1.55 km); correlation; events; 100 m stuck-pipe risk; evidence; replay; `nwis_evidence` search; advisory acknowledgement; own audit entry. Exact browser-received risk: probability `0.7455033407089751`, confidence `0.855`, `calibrated=false`. UI rounds these to 75% and 86%. The ten cited risk report/page links all returned HTTP 200 PDFs. A source-link click in full Chromium opened the built-in PDF viewer at OFF-04-DDR page 5 of 6; the rendered synthetic stuck-pipe passage matches the cited event. The viewer screenshot, report/page anchors and PDF responses are verified. Knowledge returned 17 grouped results (5 wells, 6 events, 6 reports) with citations. The previously pending mud-loss advisory was acknowledged with a browser-validation reason; its audit event appeared and chain verification passed. The previously acknowledged stuck-pipe advisory was preserved.

Critical pages were inspected at 1366×768, 1280×720 and 390×844: landing, sign in, dashboard, map, correlation, risk, Why This Alert, knowledge, advisories and audit. No document overflow or clipped modal remains. Wide tables/charts use their intended internal scroll regions. Mobile navigation opens and closes after route selection; map selection/zoom/radius, correlation keyboard event selection/range, and mobile search worked. No screenshot baseline exists, so historical pixel-regression comparison is inconclusive; these are current-render visual/layout checks.

Browser-level reduced-motion emulation passed: zero landing/auth videos, both loaded static posters, no drawer animation and no functional information lost. Both required PNG logos, both MP4s and both posters returned HTTP 200 and rendered. Only the visible film plays; the offscreen film pauses and the pause control stops both. Hero copy remains readable after its entrance; decorative generated labels remain subdued. Measured landing cumulative layout shift was below `0.012` (both full Chromium runs). Production bundle verification excludes the reference-only media and fixture/sample code. No visible old-domain wording was found. Replay, synthetic-data, uncalibrated-risk and engineering-review disclosures are present. Help provides the inline NWIS guide, glossary, safety disclosure, eight working route links and available API probes; a standalone downloadable guide is not integrated (polish).

## Console/network findings

- Final full Chromium: zero JavaScript exceptions, zero warnings, zero transport failures, zero unexpected HTTP failures. One Help probe was canceled with `ERR_ABORTED` during context/navigation transition; it produced no console error or failed UI state. Only two expected pre-login `/auth/me` 401 console messages.
- Negative auth tests intentionally returned HTTP 400. No intended golden flow returned 404, 422 or 500; no CORS/cookie/static/video/poster failures.
- Initial preview on 5175 produced an origin-guard 403. Stopping that preview produced one old-page health connection-refused message. Both were resolved by using documented/allowlisted 5173; no origin guard was weakened.
- Initial headless-shell screenshots emitted four WebGL driver `GPU stall due to ReadPixels` warnings, including the driver's repetition-limit notice. They did not recur in the final full Chromium/D3D11 run. Initial fast route/auth transitions also canceled requests with `ERR_ABORTED`; the final smoke had only the one canceled Help probe noted above.

## Verified fixes and validation

Only `frontend/src/features/nwis/nwis.css` changes application behavior: use containing-viewport drawer width instead of `100vw`; share the drawer/header padding at mobile sizes; allow long citation rows to wrap. This fixes the observed -15 px drawer offset, header oversizing and 408 px content overflow. Final mobile drawer x=0, width=375 px, client/scroll widths both 374 px. All three drawer sizes and affected risk/events/advisories/knowledge surfaces were retested. The release note now documents preview port 5173.

Frontend tests: 51/51 passed after the final CSS change. Production build: passed, 173 modules. Bundle check: passed. Lint: zero errors, three existing Fast Refresh warnings. Existing unit-test HMR-port and MapLibre bundle-size diagnostics remain documented; no refactoring was introduced. `git diff --check` passed. No new design suppression was added; the existing narrow F1 exception for the intentional legacy/dev warning banner remains.

Sanitized browser logs, scripts and bounded screenshots are stored locally under ignored `data/release-validation/f1b/`, including `browser-log.json`, `final-smoke.json`, `pdf-smoke.json`, the rendered source PDF page, auth success/expiry, map/correlation/risk/evidence, knowledge, acknowledgement/audit and mobile captures. No browser cache, credentials or OTP values are committed.

Remaining release-candidate blockers: none. Production credentials, HTTPS gateway and public deployment smoke remain future deployment tasks. This phase did not deploy, push, merge or clean up repositories.

FINAL RELEASE CANDIDATE READY
