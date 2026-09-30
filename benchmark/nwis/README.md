# SIH26121 prototype benchmark

The 46 development cases cover extraction, radius, correlation, ranking, risk, telemetry, alert suppression, evidence integrity, missing data, contradictions, prompt injection, authorization, terms, audit and no-evidence refusal. Run from the repository root:

```sh
docker compose -f infra/docker-compose.nwis.yml run --rm --no-deps backend python -m scripts.benchmark_nwis
```

`manifest.json` binds the development inputs and the eight held-out cases in `blind.json`. The development runner does not open the blind file. F1 evaluated all eight exactly once after application freeze `244b86c082174ceb9703625f70dc7d6851806705`: **8/8 passed**, with unchanged inputs/oracles and no subsequent backend tuning. The exclusive result marker prohibits reruns. See [the release record](../../docs/nwis/final_release_report.md) and [individual outcomes](../../docs/nwis/final_validation.json). These are developer-authored functional cases, not an independently collected OIL validation dataset.

The real PostGIS and local BGE/Qdrant tests are additional integration checks. These functional cases do not measure field risk calibration, AUROC, PR-AUC or NPT reduction. No such performance claims are made. Existing SIH26117 benchmark data and truth files are unchanged.

B2 adds six cases: aligned correlation tracks, paginated telemetry freshness, explicit NWIS query mode, the complete persisted assessment/source/advisory chain, deterministic offset explanations, and tie ordering by well id. Existing ranking/risk/alert cases are strengthened without duplicating case entries. The eight held-out cases are unchanged.
