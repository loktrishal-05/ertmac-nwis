# Final model comparison — Stage 2

**FINAL MODEL COMPARISON STAGE 2 READY — WAITING FOR 4B**

No final model selection. No BLIND execution. See JSON companion for exact selection, configuration, hashes and case accounting.

## Candidates

| Model | Digest | Installed | Health passed |
|---|---|---|---|
| qwen3.5:9b | 6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7 | True | True |
| qwen3.5:4b | — | False | False |

## Coverage and comparison

| Model | Selected | Runnable | Executed | Data errors | Deterministic pass / fail | Mean / median seconds |
|---|---:|---:|---:|---:|---|---|
| qwen3.5:9b | 30 | 29 | 0 | 1 | NOT_RUN | None / None |
| qwen3.5:4b | 30 | 29 | 0 | 1 | NOT_RUN | None / None |

All quality percentages use runnable-case denominator (29 currently). Per-dimension missing/not-applicable observations are disclosed, not scored as failures. No composite score. REVIEW_REQUIRED is not semantic PASS. Data errors are neither PASS nor FAIL.

29 case executions per candidate, up to 58 planner/answer requests each; 58 case executions and up to 116 requests across both candidates. Early structural failures may use fewer requests.

REF-005 remains selected. Its authoritative binding cannot resolve, so its row is DATA_BINDING_ERROR, model_called=false, deterministic_result=NOT_RUN, with no scored dimensions. Planned coverage is 29/30 per candidate; actual coverage above is separate.

## Fixed execution and invocation

Same frozen functions, evidence, validators and prompts for both models; temperature 0, seed 42, context 16384, output cap 1536, think=false, call timeout 900 seconds. No automatic retries, no native-format changes. Sequential 9B then 4B; process-scoped sleep prevention. Runtime inventory/version/digests rechecked before each candidate. Result directory creation is exclusive; interruption cannot silently rerun cases.

From repository root:

```powershell
backend/.venv/Scripts/python.exe -B -m benchmark.stage2
# Only after both candidate health checks are recorded and passed:
backend/.venv/Scripts/python.exe -B -m benchmark.stage2 --execute
```

The default command prepares reports without inference. --execute gates BOTH candidates before any evaluation; health evidence must match installed digest/runtime in final_model_runtime_readiness.json. It never downloads or health-samples models.

## Detailed metrics / safety

### qwen3.5:9b

```json
{
  "selected": 30,
  "runnable": 29,
  "executed": 0,
  "data_binding_errors": 1,
  "not_yet_executed": 29,
  "coverage": "0/30",
  "quality_denominator": 29,
  "deterministic_passes": 0,
  "deterministic_failures": 0,
  "dimensions": {
    "route": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    },
    "tools": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    },
    "human_approval": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    },
    "schema": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    },
    "citation_identity_locator": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    },
    "evidence_reference_identity": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    },
    "missing_evidence_behavior": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    },
    "refusal_status": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    }
  },
  "critical_findings_by_type": {},
  "critical_cases": [],
  "fabricated_reference_cases": 0,
  "unsafe_action_cases": [],
  "governance_hitl_cases": [],
  "injection_cases": [],
  "runtime_failure_cases": [],
  "model_requests": 0,
  "median_latency_seconds": null,
  "mean_latency_seconds": null,
  "summed_case_runtime_seconds": null,
  "input_tokens": null,
  "output_tokens": null,
  "review_required_count": 0
}
```

### qwen3.5:4b

```json
{
  "selected": 30,
  "runnable": 29,
  "executed": 0,
  "data_binding_errors": 1,
  "not_yet_executed": 29,
  "coverage": "0/30",
  "quality_denominator": 29,
  "deterministic_passes": 0,
  "deterministic_failures": 0,
  "dimensions": {
    "route": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    },
    "tools": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    },
    "human_approval": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    },
    "schema": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    },
    "citation_identity_locator": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    },
    "evidence_reference_identity": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    },
    "missing_evidence_behavior": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    },
    "refusal_status": {
      "confirmed_passes": 0,
      "confirmed_failures": 0,
      "unscored_or_not_applicable": 29,
      "denominator": 29,
      "confirmed_pass_percent_of_runnable": null
    }
  },
  "critical_findings_by_type": {},
  "critical_cases": [],
  "fabricated_reference_cases": 0,
  "unsafe_action_cases": [],
  "governance_hitl_cases": [],
  "injection_cases": [],
  "runtime_failure_cases": [],
  "model_requests": 0,
  "median_latency_seconds": null,
  "mean_latency_seconds": null,
  "summed_case_runtime_seconds": null,
  "input_tokens": null,
  "output_tokens": null,
  "review_required_count": 0
}
```

Zero counts without executions are NOT evidence of safety or performance. Injection detection and evidence identity checks do not certify semantic resistance or entailment. Runtime failures retain the frozen deterministic outcome and are also reported separately.

## Resources / timing

Stage 1 measured i5-12450H, 15.70 GiB RAM, RTX 2050 4 GiB VRAM; 9B used CPU/GPU offload. Historical 9B extrapolation is approximately 64 minutes for 29 cases; reserve 90–120 minutes, not a guarantee. 4B runtime is unmeasured. Runtime metadata includes Ollama loaded-model snapshots; no resource throughput is invented.

## Human semantic-review queue

| Case | Model | Deterministic status | Answer / citations | Review dimensions |
|---|---|---|---|---|

Empty: no candidate evaluation performed. No hosted LLM judge used.

## Infrastructure errors

[]

## Validation

32 tests passed (6 Stage 2 orchestration tests plus 26 frozen harness tests), 5.403 seconds. Confirmed generic data-error accounting, zero calls/scoring for REF-005, identical runnable IDs/prompts, blind dispatch rejection, missing/unhealthy 4B gate, and metrics denominators. All 101 frozen files match Phase 10.3. Report assertions and git diff --check passed. No model inference.

## Exact Git status

```text
 M .codex/hooks.json
?? .codex/test_hooks.py
?? .impeccable/
?? benchmark/reports/final_model_comparison_stage2.json
?? benchmark/reports/final_model_comparison_stage2.md
?? benchmark/reports/final_model_runtime_readiness.json
?? benchmark/reports/final_model_runtime_readiness.md
?? benchmark/reports/ref005_binding_resolution.md
?? benchmark/stage2.py
?? benchmark/test_stage2.py
?? claudex-loop/
?? docs/tooling-health.md
```
