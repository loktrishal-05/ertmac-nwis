# Risk-aware local model routing

The production primary is **qwen3.5:9b**. **qwen3.5:4b** is eligible only for explicitly bounded internal work. A request calling itself “simple” cannot select a model or grant itself authority.

## Architecture and authority

The existing execution architecture is preserved:

1. HTTP authentication/RBAC and deterministic preflight run before any model selection or inference. Voice/operational authorization and identity-bound replay remain unchanged.
2. Verified exact knowledge and verified CAG packs still return through the existing governance boundary without model calls.
3. Existing deterministic adaptive rules choose Hybrid RAG, MGS or the agentic path. The optional System1 planner remains a strategy adviser with a strict schema.
4. The planner now uses `model_routing.generate_bounded`. It selects a cached role profile from the **existing** `ModelGateway` and runtime adapter. No second model stack, model server, downloader or transport was added.
5. All existing graph/router/specialist generation uses the primary profile through `get_model_gateway()`. This includes graph calls made outside `/query`. The graph topology, tools and checkpoint behavior are unchanged.
6. Existing evidence/citation checks, governance, independent human review and advisory-release gates remain authoritative. Choosing 9B never establishes sufficiency, safety, permission or approval.

Authority order remains **deterministic security > RBAC > HITL/governance > execution path > model routing > generative reasoning**. The existing pre-generation safeguards and post-generation governance checks retain their positions; routing cannot turn off either.

The low-level explicit `ModelGateway(settings, runtime=...)` constructor remains available for existing adapter tests and standalone tooling. Production agents use the role-aware getter; `MODEL_NAME` and the legacy `SYSTEM1_MODEL` cannot silently select 4B for primary production reasoning.

## Deterministic routing rules

`RiskSignals` is a strict, frozen server-side Pydantic model. It is not accepted in `QueryRequest`, populated from a model's confidence, or inferred from client role claims.

| Class | Selection and reason |
|---|---|
| `FAST_LOW_RISK` | 4B only for an explicitly declared bounded strategy, formatting, schema transformation, metadata extraction, classification or helper-text task, with no risk signal. |
| `SAFETY_CRITICAL` | 9B for safety context/language, approval-bearing work, shutdown/startup/isolation or environmental/compliance reasoning. |
| `COMPLEX_SYNTHESIS` | 9B for multiple documents, MGS, multi-agent work or synthesis signals. |
| `DEEP_EVIDENCE` | 9B for evidence/plant reasoning, insufficient or conflicting evidence, missing verified knowledge, uncertain P&ID/OCR, critical tag verification or high-risk tools. Hybrid RAG and the agentic path always require primary, even if a caller labels the task formatting. |
| `FORCE_PRIMARY` | 9B for explicit force, previous fast failure, unknown/unclassified tasks or input outside the fast bounds. |

Fast input is limited to 2,048 characters, including the actual message content, and 256 generated tokens. Unclassified or non-ASCII user context defaults to primary because the supplemental language rules are English-only. System instructions are trusted call-site code; their authorization prohibitions are not mistaken for risky user requests. Tool-role input increases caution and the bounded helper never supplies executable tools.

The first production fast consumer is the **existing optional System1 strategy planner**. The reusable internal helper supports other listed bounded operations, but this change does not add formatting endpoints, user-facing helper features or a new `/query` mode. Ordinary company questions, even short ones, do not become fast answers. A planner classifying a request is not deciding whether evidence exists; all subsequent evidence-dependent generation remains primary.

## Escalation and failure behavior

Before a bounded call, deterministic signals for insufficient evidence, multiple documents, conflicts, safety, approval, low-confidence OCR (below the existing 0.6 threshold), P&ID uncertainty, risky tools, missing verified knowledge, critical tags, multi-agent synthesis or prior fast failure select 9B immediately. Callers must supply known structured risk facts; text heuristics can only increase caution.

After a 4B attempt:

- Runtime unavailability, timeout or runtime error records `fast_runtime_failure` and may attempt 9B once.
- Invalid schema, duplicate JSON keys, truncation, unexpected finish/tool-call output or a deterministic caller-contract rejection records `fast_contract_failure` and may attempt 9B once.
- Fast schema repair is disabled. The failing response is not returned as a successful answer; the primary retry receives the original task, not an appended failed model response.
- The primary bounded attempt uses the same schema, deterministic contract and output bounds. If it fails, its error propagates. There is no fallback to 4B.
- Failure of the optional planner may still select the existing deterministic **primary** agentic path. That is a path fallback, not a model downgrade. A primary graph failure retains existing safe errors/refusals and may use existing primary-only retrieval-path fallbacks.
- Configuration errors fail closed rather than switching profiles. Missing models are not downloaded; the helper checks the installed inventory and the runtime retains its existing unavailable-model behavior.

The helper makes at most two logical generation calls: fast then primary, or primary alone. Existing runtime transport retries and primary graph schema-repair behavior remain separate. Graph retrieval and evidence-sufficiency checks already operate behind a primary-only gateway, so late evidence/OCR/approval signals cannot leave an evidence answer on 4B.

## Configuration and locality

```dotenv
FAST_MODEL=qwen3.5:4b
PRIMARY_MODEL=qwen3.5:9b
MODEL_NAME=qwen3.5:9b
MODEL_RUNTIME=ollama
MODEL_BASE_URL=http://127.0.0.1:11434
SYSTEM1_ENABLED=false
```

`FAST_MODEL` and `PRIMARY_MODEL` have the shown safe defaults and are restricted to their benchmark-approved tags. Swapping the roles, hosted model names and cloud-offloaded tags is rejected. Changing approved profiles requires an explicit policy/code review, not a client request. `MODEL_NAME` retains its existing explicit configuration requirement for standalone gateway compatibility, but does not override production roles. `SYSTEM1_MODEL` is retained for configuration compatibility and is no longer a routing authority; use `FAST_MODEL`.

`SYSTEM1_ENABLED` remains opt-in. Its existing timeout bounds each bounded generation attempt. The default getter caches primary and fast profiles separately; configuration is process-scoped, so restart after environment changes. Config validation is repeated by the routing policy because Pydantic `model_copy` bypasses field validation.

Existing local/private endpoint allowlisting, hosted-provider denial, cloud-tag denial, private DNS checks and disabled proxy/redirect inheritance remain in force. No hosted inference, model downloads, telemetry stack or chain-of-thought storage was added. LangSmith/LangChain environment hardening is unchanged. vLLM remains the existing unimplemented adapter; this feature does not claim to add vLLM support.

## Observability and client compatibility

`QueryResponse.execution` remains an optional dictionary; no required request/response field changed. Existing clients can ignore the additive routing fields:

- `requested_path`, `selected_model` (also exposed as `model_selected` for compatibility), `model_role`, `routing_class`, `routing_reasons`
- `escalated`, `escalation_reason`, `routing_fallback_reason`, `routing_history`

Existing `execution_path`/`fallback_reason` describe execution-path selection; `routing_fallback_reason` distinguishes model fallback. `model_selected` is the planned profile for the current stage, while `model_used` and `model_stages` describe actual observed generation calls. Zero-generation verified/CAG paths do not invent a selected model. A planner's fast-to-primary escalation remains visible after the primary graph stage updates the current selection.

The existing request-local counters record model calls (including failures), stage, actual model, latency, input/output tokens when supplied, and routing metadata. A schema-invalid successful runtime response still contributes tokens and latency; its contract failure is explained by routing escalation metadata. Counts are gateway generation calls, not inventory requests or each HTTP transport retry. Missing token usage remains null rather than an invented estimate.

The same execution structure is persisted by the existing run-step tracing and governed revision paths; replay retains the original governed execution metadata. Failed graph traces receive the routing snapshot too. Primary trace/proof model labels now match the primary profile rather than a legacy `MODEL_NAME` value. No query text, generated answer, raw invalid output or private reasoning is added to routing metrics.

## Frozen benchmark rationale

The existing [Stage 3 selection report](../benchmark/reports/final_model_selection_stage3.md) selects 9B as primary and limits 4B to bounded fast/System1 tasks. Its DEV/VALIDATION comparison records:

| Evidence | 9B | 4B |
|---|---:|---:|
| Critical failure records | 1 | 4 |
| Evidence identity pass / fail / unscored | 27 / 1 / 1 | 25 / 4 / 0 |
| Tool pass / fail / unscored | 13 / 15 / 1 | 8 / 21 / 0 |
| Supplied semantic pass / fail / uncertain | 24 / 4 / 1 | 17 / 12 / 0 |
| Median case latency (seconds) | 107.724 | 42.296 |

4B is materially faster. Its repeated failure to pursue available evidence, followed by missing-evidence claims and weaker synthesis, rules it out as the authoritative evidence-dependent plant reasoning model. 9B has fewer critical failures and stronger retrieval/grounding and supplied semantic results, but still has defects and receives no autonomous plant authority.

Semantic counts are the selection report's attributed, user-supplied independent model-review summary, not fresh human adjudication or independently reconstructed labels. Empty citations can make identity checks vacuous. Latencies are historical benchmark measurements, not production SLAs. No benchmark prompts, cases, truth, scores, results or artifacts were changed; no BLIND or model evaluation was rerun.

## Validation and limitations

`backend/tests/test_model_routing.py` covers fast eligibility, safety, synthesis, approval, P&ID/OCR uncertainty, every structured escalation signal, actual bounded structured calls, contract/runtime escalation, primary failure without downgrade, config/hosted rejection, RBAC, HITL, execution metrics and identity-bound replay. Tests use the existing gateway with mocked local runtimes, never real model inference. Existing adaptive tests use the same role getter as production and retain their preflight, path, evidence and governance assertions.

The active production surface deliberately keeps all evidence-oriented graph generation on 9B. New internal bounded consumers must provide their risk facts and deterministic semantic contract; schema validity alone is not factual correctness. English text heuristics are supplemental, not a universal intent detector. Local model tags can be retargeted by a host administrator: artifact provenance, network egress controls, concurrency/capacity and production latency still require deployment validation.

## Recovery and validation (2026-09-27)

Recovered the existing uncommitted A1 routing policy, role-aware gateway, adaptive planner integration, request-local metrics, primary trace/proof labels, regression tests and draft documentation. No work was reset or discarded. The worktree HEAD is `9f1ec42`; Git has no separate Codex/Kimi commits or patch snapshots, so individual uncommitted lines cannot be reliably attributed to either session. No independently identifiable incorrect Kimi patch was found. The unfinished items were the frozen-asset guard and final validation/documentation. Recovery also added the requested `selected_model` compatibility field and an explicit trusted `complex_synthesis` signal.

Kimi's reported `ModuleNotFoundError: No module named 'langgraph'` was an interpreter/dependency-environment issue. The existing shared venv imports LangGraph successfully. Testing confirmed `app.__file__` resolves to `C:/Users/Lohith k/Desktop/sovereign-model-routing/backend/app/__init__.py`; only installed dependencies come from the main worktree's venv. No new venv or dependencies were installed, and main-worktree application source was not edited.

Run from the isolated backend directory using the shared interpreter:

```powershell
Set-Location 'C:/Users/Lohith k/Desktop/sovereign-model-routing/backend'
$routingPython = 'C:/Users/Lohith k/Desktop/sovereign-agentic-workbench/backend/.venv/Scripts/python.exe'
$env:MODEL_NAME='qwen3.5:9b'
$env:WORKBENCH_TEST_POSTGRES='1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& $routingPython -c "import app, langgraph; print(app.__file__)"
& $routingPython -m pytest tests/test_model_routing.py tests/test_advanced_a2.py tests/test_advanced_a3.py tests/test_model_gateway.py tests/test_phase11_security.py tests/test_evaluation_asset_guard.py tests/test_phase5e.py -q -p no:cacheprovider
& $routingPython -m pytest tests -q -p no:cacheprovider
git diff --check
```

The full suite needs write permission to this isolated worktree for the existing sensor-feature artifact test, and local PostgreSQL access. Real-model inference remains opt-in.

| Validation | Result |
|---|---|
| Targeted routing, authority, gateway and integrity tests | 156 passed; 58 subtests passed; 0 failures/errors |
| Full backend, including PostgreSQL integration | 715 passed; 0 failed; 0 errors; 1 skipped; 101 subtests passed (163.75 seconds) |
| Skipped test | Existing opt-in live local-model query smoke test |
| Warning | Starlette/AnyIO deprecated `BlockingPortal` alias; one dependency warning |
| Diff whitespace check | Passed |
| Frozen benchmark/report/evaluation paths | No Git changes |

Two initial pytest runs reached 100% without reported failures but stalled before summary/exit and were interrupted; they are not counted as successful validation. The completed runs above disabled third-party pytest plugin autoload and the cache provider. The first completed full run under the filesystem sandbox reported **714 passed, 1 failed, 1 skipped**: `test_maintenance_and_sensor_routes_use_the_injected_session` received HTTP 503 because its write to `data/processed/sensors/features/` raised `PermissionError`. The full suite then passed with the required filesystem permission, without changing application code or that test.

### Frozen hash root cause: CHECKOUT_LINE_ENDING_EFFECT

`core.autocrlf=true`; `git ls-files --eol` reports `i/lf w/crlf` for the pinned assets. For the evaluation spec and all four manifest assets, Git HEAD blob SHA-256 values exactly match the existing expected hashes. Their working bytes differ only by uniform LF-to-CRLF checkout conversion. The earlier three failures came from hashing raw checkout bytes, not from a real content mutation.

Both integrity-test callers now use the same guard. It reads the committed Git bytes, requires working bytes to equal those bytes or their exact uniform CRLF checkout form, and hashes the canonical bytes against the **unchanged** pinned SHA-256. It does not merely trust HEAD or normalize arbitrary whitespace: edited content, mixed line endings, bare carriage returns and changed trailing newlines fail. Committed content changes still fail the pinned hash comparison. Missing Git objects/files fail closed. A synthetic regression exercises accepted checkout encodings and rejected mutations without editing any frozen asset.

No benchmark reports/results, frozen files or expected hashes were modified. No model benchmark or BLIND evaluation was rerun. No frontend, A2, automatic commit or integration was performed. A1 is ready for integration.
