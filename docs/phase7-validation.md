# Phase 7 validation

## Result

PHASE 7 COMPLETE. No remaining BLOCKER/HIGH issue identified in this scope.
No commit, Phase 8 work, or edits to `frontend/src/App.jsx`, `.codex/`, or
`claudex-loop/`. No schema migration was needed.

## Executed validation

From `backend`, existing `.venv` and `PYTHONPATH=tests`:

| Check | Result |
| --- | --- |
| `WORKBENCH_TEST_POSTGRES=1 python -m unittest test_phase7 test_phase5f_security test_phase6 -v` | 60 passed, 30.400 seconds |
| `WORKBENCH_TEST_POSTGRES=1 python -m unittest discover -s tests -v` | 532 run: 531 passed, 1 skipped, 142.727 seconds |
| Final `python -m unittest test_phase7 test_model_gateway -q` | 57 passed, including 18 Phase 7 tests |
| `python -m compileall -q app scripts tests` | PASS |
| `docker compose -f infra/docker-compose.yml config --quiet` | PASS |
| Frontend `npm run build` | PASS after sandbox escalation |
| Frontend `npm run lint` | PASS |
| `git diff --check` | PASS |

The final run includes the cloud-model-tag test added after the full run.
Totals overlap; do not add them as unique tests. The only full-suite skip was
the opt-in live local-model `/query` test. Real PostgreSQL security, authorization,
evidence, and concurrency tests were enabled. Existing agent-query regressions,
Phase 6 integration, Phase 5 governance, and benchmark guards passed.

Initial failures were not hidden: one Phase 7 test exposed Windows normalization
of `s3://...` paths; the guard was corrected and subsequent runs passed. The first
frontend build failed because the sandbox denied esbuild's child process (EPERM);
the approved retry passed. No frontend source repair was performed.

Detailed local output is retained in ignored root logs:
`phase7-targeted-results.log`, `phase7-full-results.log`,
`phase7-live-results.log`, and `phase7-live-server.log`.

## Live local validation

A temporary loopback Uvicorn process ran the current code and was stopped after
the check. The new `scripts/validate_local_runtime.py --backend-url ...` validated
real HTTP endpoints on 2026-09-22 at 06:31 UTC:

- `/health`: 200, process healthy.
- `/ready`: 200; configuration, PostgreSQL, Qdrant, and model all true.
- PostgreSQL: real SELECT 1 succeeded; existing Docker PostgreSQL 17 healthy.
- Qdrant: real `/readyz` succeeded; existing Docker Qdrant v1.17.0 running.
- Ollama: runtime metadata reachable, configured `qwen3.5:9b` installed.
- `/sovereignty/proof`: 200; inference, PostgreSQL, and Qdrant classified local;
  local filesystem; hosted configuration false; external calls zero;
  `network_egress_enforced=false`; config version `phase7-v1`.

No model inference, data mutation, or plant action was performed by this runtime
check. Zero local inference attempts in that worker is therefore expected.
Installed-model readiness is not proof of output quality or model load capacity.

## Focused assertions

Tests reject hosted/public model endpoints even if allowlisted, non-private DNS,
redirects, credentials/query parameters, cloud tags, public storage endpoints,
cloud filesystem URIs, and dirty runtime endpoint configuration. They accept
loopback, explicitly allowlisted RFC1918 addresses, and Docker/on-prem names.
They verify actual dispatch-counter increments, client inability to reset counts,
configuration-derived proof, redaction, inexpensive health, dependency failure
503s, and explicit vLLM-not-implemented behavior.

## Claims and limits

IMPLEMENTED: application-level local/on-prem sovereignty controls.

NOT CLAIMED: absolute firewall/physical network isolation. Counts are worker-
lifetime observations, reset on restart, and do not cover upstream behavior of
the model server or unrelated processes. DNS is checked, not pinned. Named
local/private endpoints and filesystem paths do not attest physical deployment.
The existing Compose architecture and persistent volumes are reused unchanged.
Provisioning downloads remain explicit and separate from local inference.
