# Phase 4R validation record

This document records the validation commands and their interpretation. A dependency-unavailable result is recorded as unavailable, never as a pass.

## Deterministic checks

- `python -m compileall -q backend/app`
- backend unit-test discovery, including Phase 3, gateway, orchestration, specialist, schema, and Phase 4R regression tests
- evaluation asset hash guard
- `git diff --check`
- `alembic check` / offline migration consistency
- `docker compose config`
- frontend build and lint

The Phase 4 completion document's 267-test count was inaccurate. The repaired suite executed **279 tests: 278 passed and 1 environment-dependent error**. The remaining error is the live `/query` foundation smoke test, which returned HTTP 500 because PostgreSQL/Qdrant are unavailable; it is reported as unavailable rather than converted into a pass.

## Targeted regressions

The Phase 4R suite covers monotonic nested approval propagation, model informational-label bypass, required/unknown/mismatched citations, arbitrary and cross-asset thresholds, unsupported diagnostic observations, OCR provenance, deterministic refusal text, and contextual authorization-language handling. Existing specialist tests were updated where their fixtures relied on the retired free-number threshold behavior or stale `not_implemented` status claims.

## Live checks

PostgreSQL, Qdrant, and Ollama/qwen3.5:9b are reported separately. A `/query` smoke test and representative Knowledge, Safety, Maintenance, and Optimization queries are marked **not run** when any dependency is unavailable.
