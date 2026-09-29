# SIH26121 prototype benchmark

The 46 development cases cover extraction, radius, correlation, ranking, risk, telemetry, alert suppression, evidence integrity, missing data, contradictions, prompt injection, authorization, terms, audit and no-evidence refusal. Run from the repository root:

```sh
docker compose -f infra/docker-compose.nwis.yml run --rm --no-deps backend python -m scripts.benchmark_nwis
```

`manifest.json` binds the development inputs and the eight held-out cases in `blind.json`. The development runner does not open the blind file. The held-out cases have concrete inputs and oracles; they are reserved for independent review and have not been executed or used to tune this implementation. They are developer-authored, not an independently collected OIL validation dataset.

The real PostGIS and local BGE/Qdrant tests are additional integration checks. These functional cases do not measure field risk calibration, AUROC, PR-AUC or NPT reduction. No such performance claims are made. Existing SIH26117 benchmark data and truth files are unchanged.

B2 adds six cases: aligned correlation tracks, paginated telemetry freshness, explicit NWIS query mode, the complete persisted assessment/source/advisory chain, deterministic offset explanations, and tie ordering by well id. Existing ranking/risk/alert cases are strengthened without duplicating case entries. The eight held-out cases are unchanged.
