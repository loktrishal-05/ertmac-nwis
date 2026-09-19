# Phase 4R repair record

Phase 4R repairs deterministic correctness and evidence handling discovered in the independent Phase 4 audit. It does not implement Phase 5 approval authority, authentication, audit chaining, evidence manifests, plant-control writes, or hosted inference.

## Status

| Area | Phase 4R disposition |
|---|---|
| Specialist routes | Implemented and advisory |
| `human_approval_required` | Monotonic graph state only; not authorization |
| Model approval metadata | Ignored for authority; action policy is deterministic |
| Citations | Required for grounded specialist prose; IDs and locators checked |
| Maintenance limits | Typed applicability required; free numbers are unavailable |
| OCR provenance | Forwarded into evidence blocks and marked explicitly |
| Authorization-language validator | Supplemental heuristic only |
| Evidence integrity | Provenance carried, cryptographic binding deferred to Phase 5D |
| Approval workflow | Not implemented; Phase 5 responsibility |

The graph reducer ORs approval requirements and retains the most severe action class. Specialist output cannot clear a requirement set by deterministic policy. Safety action text classified as operational is upgraded from an informational model label and requires review. `approved`, `not_required`, `safe`, and `informational` model labels have no authorization effect.

Grounded answers and action-adjacent recommendations require citations. Citation IDs must belong to the current evidence set and supplied locators must match. Maintenance hypothesis and sensor interpretation evidence references are checked against the same set. This is reference validation, not cryptographic integrity or semantic entailment.

Maintenance no longer treats the first number in retrieved text as an engineering limit. A limit is usable only when asset, measurement, unit, and cited source text agree. Otherwise the route reports `threshold unavailable / insufficient authoritative limit evidence`; D-014 remains an operator decision.

Observation validation rejects unsupported causal certainty and requires a recorded measurement/event marker. Diagnostic explanations belong in explicitly evidenced hypotheses. OCR blocks preserve source hash, document/version references, image/region references, confidence, and status, and tell the model that OCR cannot establish topology, flow, connectivity, valve state, or isolation.

Optimization forwards bounded deterministic feature summaries for each returned sensor, including the feature object and anomaly observations. The model explains those values; it does not own their arithmetic. Read-only retrieval no longer creates a missing Qdrant collection or payload index. Ollama requests disable environment proxy inheritance, and LangSmith/LangChain tracing is forced off in the on-prem process.

The authorization-language detector normalizes whitespace and distinguishes direct language from quoted, documentary, explanatory, negated, and hypothetical contexts. It is used as a bounded output-quality signal only. Passing it never grants authorization.

## Decisions that remain open

D-002, D-004, D-009, D-012, D-014, and D-015 remain provisional human decisions. In particular, the relevance floor remains the configured `WORKBENCH_KNOWLEDGE_RELEVANCE_FLOOR` value of `0.0` (the unprefixed spelling remains a compatibility alias); it is not a calibrated safety threshold. Phase 5 must define the trusted approval boundary and live-path acceptance.
