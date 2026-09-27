# Phase 11 â€” Security, sovereignty and governance

Date: 2026-09-27. Repository: `sovereign-agentic-workbench`, base commit `86e895f`.
This audit resumes the existing Phase 11 changes. No benchmark inference, BLIND rerun, prompt tuning, frontend work, feature expansion or commit was performed.

## Policy and scope

**ALL COMPANY QUERY ACCESS REQUIRES AUTHENTICATION.** This includes informational, preflight-refused, replayed, operational and voice queries. `/query` requires a server-authenticated requester, reviewer or administrator. Missing authentication returns 401 before body validation; authenticated malformed requests still return 422. Client role headers and body fields confer no authority.

Requester identity propagates through replay, revision creation, governance and audit. Operational and voice authorization remains in place. The route's unreachable anonymous branch was removed; the corresponding direct-call test now checks anonymous HTTP access through FastAPI's actual dependency chain.

Historical bindings with `requester_user_id = None` cannot be claimed by an authenticated requester: identity mismatch returns a conflict. The existing approval gate also refuses review of an unverified requester. No identity migration was introduced; resubmit under a **new request ID** as an authenticated requester. Internal service fixtures can still represent legacy unowned records, but this does not grant HTTP access or review authority.

## Findings and fixes

| ID | Classification | Severity | Result |
|---|---|---|---|
| P11-01 | REAL VULNERABILITY | HIGH | Fixed previously unguarded company data endpoints: document/P&ID operations require admin; knowledge/maintenance/sensor reads require an authorized company role; maintenance/sensor ingestion additionally requires admin. |
| P11-02 | REAL VULNERABILITY | HIGH | Fixed client-selected retrieval scope: `/knowledge/retrieve` rejects non-internal scopes and supplies `internal` server-side when omitted. |
| P11-03 | REAL VULNERABILITY | HIGH | Fixed request-ID replay/revision access without requester binding. Both existing-record and post-insert race checks compare authenticated identity. |
| P11-04 | REAL VULNERABILITY | HIGH | Fixed advisory release without requester ownership: shared release service checks fresh database role and requester ownership under `no_autoflush`; forged or dirty in-memory roles are insufficient. Existing approval, evidence, expiry, revocation, locking and mandatory-audit gates remain. |
| P11-05 | HARDENING | MEDIUM | All `/query` access now requires authentication, including informational preflight. Production authentication was not weakened for tests. |
| P11-06 | TEST MIGRATION | LOW | Repaired the 10 reported auth-affected tests with server-side actors. Preserved validation, provenance, idempotence and response assertions. Also migrated three opt-in PostgreSQL query tests to real requester login and one direct-call anonymous assertion to HTTP. |
| P11-07 | HARDENING | LOW | Preserved hosted-tracing prevention and local tracing code. Removed the line-ending-only `graph.py` worktree change. Added a legacy unowned-binding regression to the existing Phase 11 security tests. |
| P11-08 | HARDENING | MEDIUM | Upgraded only venv pip from 24.0 to 26.2.1. OSV scan: 12 advisory IDs on pip before, zero findings across 178 installed packages after. Advisory aliases can describe the same underlying issue; 12 IDs do not imply 12 distinct vulnerabilities. Project dependency declarations unchanged. |
| P11-09 | ENVIRONMENT LIMITATION | LOW | Previous Windows native-import failures were not hidden by application changes. Fresh sklearn, transformers and ujson imports succeeded in this session. Historical failure cause remains unproven; see validation results for full native execution. |

## Boundary review

| Boundary | Evidence and result | Residual limits |
|---|---|---|
| Hosted AI and telemetry | `agents/__init__.py` forcibly disables inherited LangChain/LangSmith tracing and clears endpoints before graph imports. Fresh-process probe with tracing enabled and hosted endpoints confirmed all four values reset. Existing tracing regressions retained. `agents/tracing.py` unchanged. | This verifies application configuration and tested paths, not host-wide packet capture or a firewall attestation. Local traces may contain queries when configured; protect storage and retention. |
| Local model execution | `model_gateway/registry.py` permits only configured local/private allowlisted runtimes, denies hosted providers/cloud model tags; runtime clients disable environment proxies and redirects. Embedding/reranking loaders use local artifacts and disable remote code. | Provision models separately. Enforce outbound network policy independently; private DNS resolution checks have a network/DNS TOCTOU limitation. |
| Authentication/RBAC | `api/deps.py`, `core/security.py`, `routes/auth.py`: opaque random session tokens, stored hashes, expiry/revocation, Argon2id passwords, server-loaded roles; router and route dependencies enforce company roles. | TLS, Secure cookies, login throttling, ingress/body limits and least-privilege accounts are deployment requirements. Default cookie setting supports local HTTP development. |
| HITL and model self-approval | `services/governance.py`, `approval.py`: model authority fields are removed; drafts start pending; independent database-authorized reviewer required; self-approval denied. Requester-bound replay and release deny cross-user access. | Approval is human review of an advisory draft, never permission to actuate equipment. Legacy unowned records require resubmission. |
| Advisory release | Fresh approval/evidence checks, expiry/revocation checks, row-lock recheck and mandatory audit commit precede successful release. PostgreSQL acceptance suite tests races and audit failure. | Release is a read of advisory content plus audit event, not a plant command. The legacy placeholder approval POST performs no approval. |
| SCADA/DCS/PLC | `agents/registry.py` exposes seven registered read-only tools; no plant-write adapter or dynamic client plugin loader. Operational and automation routes produce records/summaries only. | Maintain this prohibition when adding integrations. Local database/audit writes are not plant writes. |
| Tool authorization | Closed tool names, strict argument models, bounded inputs, server graph context and retrieval scope; no model-created execution capability. | Registry registration is trusted application code. It is not a sandbox against a malicious process administrator or arbitrary Python code. |
| Prompt injection | Deterministic preflight, untrusted document/user content, citation validation, authorization-language checks and governance after generation. Replays re-run current preflight. PostgreSQL injection tests preserve zero-model-call refusal checks. | Heuristics cannot prove detection of every linguistic attack. Security authority rests in deterministic roles, tools and approval gates. |
| Evidence identity | Canonical request/proposal hashes and evidence manifests bind source/version/quote/locator identities; release re-verifies evidence. PostgreSQL triggers reject manifest mutation. | Source storage and database administration remain trusted infrastructure. |
| Verified registry | `verified_knowledge.py` rechecks authoritative role, independent review, exact matches, source content/hash/version/scope, approval validity and lifecycle. OCR is excluded from verified promotion. | No inferred trust from a model answer or semantic similarity. Registry outages fall back to the governed path. |
| Stale/revoked data | Registry, packs and release recheck lifecycle, source revision/hash and approval revocation/expiry. Regression suites exercise stale/revoked sources and changed content. | Ordinary retrieval is evidence, not an assertion of human verification; operators must maintain source lifecycle data. |
| CAG/MGS/adaptive routing | `adaptive_execution.py`, knowledge-pack and MGS tests: planner advises bounded strategy only; it cannot override scope, preflight, trust, source IDs or HITL. Stale packs fail closed; MGS maps to original sources. | Optional planner/model availability affects functionality, not authorization. |
| OCR/P&ID uncertainty | `pid_evidence.py` validates manifest/source/artifact identity, confines paths and preserves raw OCR. Low confidence remains ambiguous; other OCR remains unverified, never proven equipment identity/topology. | Human verification of drawing interpretation remains necessary. |
| Voice/STT/TTS | `local_voice.py` validates local/private endpoints, DNS, audio size/type, disables redirects/proxies, retains original language and requires transcript confirmation. TTS adds advisory wording. Auth and HITL remain common gates. | Local adapter service implementation, network placement and audio-handling policy must be independently trusted; unavailable service falls back to text. |
| n8n/webhooks | `product_integration.py`: HMAC SHA-256 over timestamp/nonce/kind, constant-time comparison, five-minute freshness window, durable unique nonce, current reviewer/admin principal, summary-only schema. | Manage signing-secret rotation and n8n host security. Earlier n8n templates must not be treated as authority to approve or write to plant systems. |
| File upload/path traversal | Local staged source paths are resolved and checked under allowed roots; PDF/CSV size/type/row bounds and P&ID artifact bindings are enforced. Admin-only ingestion is regression-tested. | Restrict filesystem writes by untrusted local users; path checks do not replace OS isolation. Proxy limits and parser patching remain required. |
| PostgreSQL/Qdrant | Settings reject public endpoints; compose publishes both on 127.0.0.1. Qdrant client disables environment proxy inheritance. | Development database password and database superuser are not production credentials/roles. Qdrant authentication, DB TLS where appropriate, ACLs, backups and volume encryption require deployment configuration. |
| CORS/debug/network | FastAPI debug remains off; credentialed CORS uses explicit localhost origins, never wildcard origins. | Health/model/tool/sovereignty metadata and API docs are public by design. Restrict ingress in production; CORS is not network access control. No claim of enforced egress isolation. |
| Audit integrity | Hash-linked append-only records, sequence/head/checkpoint verification and PostgreSQL mutation guards are **TAMPER-EVIDENT**. Mandatory governance audit failure rolls back authority changes. | A database/host administrator who can replace all state is outside the protection boundary. Use independent checkpoint retention and least-privilege database roles. |
| Secrets | Current tracked/nonignored text pattern scan: zero high-confidence candidates. Three prior candidates manually revalidated as false positives. `.env` is not tracked. | Pattern scanning is not proof of absence; ignored runtime secrets and historical scanning limitations are explicit in the scan evidence. No credential values were printed. |

## Secret candidate disposition

- `backend/app/services/execution_observability.py:14`: ContextVar reset token, not an authentication token.
- `backend/app/services/sparse.py:15`: tokenization regular expression, not a secret.
- `infra/n8n/05-wb-operational-summary.json:40`: environment variable lookup, not an embedded signing secret.

The resumed scan covered 650 current tracked/nonignored text files up to 5 MB and retained the prior history scan evidence without claiming a fresh historical scan. The earlier frontend dependency audit reported zero findings; frontend dependencies were not changed or freshly rescanned in this backend phase.

## Validation

Final counts and exact git status are recorded in the companion JSON and in the final validation record below. Test logs remain local ignored artifacts under `docs/.phase11_*.log`.

The original 10 auth failures are fixed (3 agents, 2 Phase 5A, 3 structured, 1 P&ID, 1 foundation). The repaired target run passed 26 tests. The security selection passed 300, failed 0, errors 0, skipped 23. The first full resumed run, with the pre-existing test-only ujson fallback, passed 651, failed 0, errors 0, skipped 46. The real PostgreSQL Phase 5F security acceptance suite subsequently passed all 22 tests with no skips after migrating its three anonymous query fixtures.

No application dependency import behavior was changed. `docs/.phase11_test_runtime/sitecustomize.py` is test-only and must never be added to production `PYTHONPATH`. A native full-suite run passed 651, failed 0, errors 0, skipped 46, without the fallback. The historical Windows/native-import issue is not reproducible in this session; no OS policy change or native-package repair was needed or performed. A final PostgreSQL-enabled full run is recorded below.

Reproduction from repository root (PowerShell):

```powershell
$env:PYTHONPATH="$PWD/backend;$PWD/backend/tests"
$env:WORKBENCH_TEST_POSTGRES='1'
backend/.venv/Scripts/python.exe -m unittest discover -s backend/tests -v
git diff --check
```

For the historical fallback run only, prepend `$PWD/docs/.phase11_test_runtime` to `PYTHONPATH`. Keep live-model smoke opt-in disabled; no benchmark evaluation is required by these commands. PostgreSQL tests use their existing uniquely named disposable schemas.

## Deployment assumptions and remaining risks

No unresolved critical/high application defect is established by this review. Sovereignty is **CONDITIONAL** on independently enforced on-premise networking and deployment controls, not on an application-reported zero call count alone.

Medium deployment risks: absent external egress attestation; development cookie/DB defaults if deployed unchanged; unverified production TLS, rate limits, database least privilege, Qdrant protection and storage/backup access controls. Low limitations: legacy identity compatibility, public operational metadata/API documentation, local query-trace retention and bounded pattern-based secret coverage. These are production deployment gates, not new feature work or a claim that the local development configuration is production certified.

## Files and exclusions

Production changes are limited to API authorization/scope and governance/approval binding. Test changes migrate authenticated fixtures and add Phase 11 regressions. Audit evidence and this report document validation and remaining assumptions. Pip changed only within the ignored backend venv.

`benchmark/reports/final_model_runtime_readiness.json` contains a pre-existing unrelated runtime-health change and is **excluded from Phase 11**. `claudex-loop` and its local contents are also excluded and preserved. All paths in the recovered benchmark hash baseline were checked without rerunning or modifying benchmark truth/results; no mismatches were found. `graph.py`, `agents/__init__.py` and `agents/tracing.py` have no Phase 11 semantic changes. Nothing was staged or committed.

## Final validation record

**PHASE 11 COMPLETE ? READY FOR FEATURE EXPANSION.** No feature expansion was started.

| Run | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| auth_targeted | 26 | 0 | 0 | 0 |
| security_selected | 300 | 0 | 0 | 23 |
| full_with_test_runtime | 651 | 0 | 0 | 46 |
| full_native | 651 | 0 | 0 | 46 |
| postgres_security | 22 | 0 | 0 | 0 |
| full_backend | 696 | 0 | 0 | 1 |

Final full run: 697 total, PostgreSQL enabled, native dependencies, no ujson workaround. The only skip is the opt-in live-model `/query` smoke. No environment-only failures remain. `git diff --check` passes. All 168 frozen baseline hashes match.

LANGSMITH / HOSTED TRACING: PASS. SOVEREIGNTY: CONDITIONAL. Hosted AI/tracing in the audited confidential path: NO. SCADA/DCS/PLC write capability: NO. Remaining HITL bypass found: NO. Real secrets found: NO within the documented scan scope.

Remaining application release blockers: none found. Production deployment gates remain as listed above. Unresolved critical/high findings: none; medium/low residual risks are deployment and compatibility limitations, not concealed test failures.

Phase 11 files are all entries below except the two explicit exclusions. Evidence logs are ignored local artifacts; machine-readable results and log hashes are retained in the JSON. No files were staged or committed.

Exact `git status --short`:

```text
 M backend/app/api/router.py
 M backend/app/api/routes/knowledge.py
 M backend/app/api/routes/maintenance.py
 M backend/app/api/routes/query.py
 M backend/app/api/routes/sensors.py
 M backend/app/services/approval.py
 M backend/app/services/governance.py
 M backend/tests/test_advanced_b.py
 M backend/tests/test_agents.py
 M backend/tests/test_foundation.py
 M backend/tests/test_phase5a.py
 M backend/tests/test_phase5e.py
 M backend/tests/test_phase5f_security.py
 M backend/tests/test_pid.py
 M backend/tests/test_structured.py
 M benchmark/reports/final_model_runtime_readiness.json
 ? claudex-loop
?? backend/tests/test_phase11_security.py
?? docs/.phase11_advisory_details.json
?? docs/.phase11_baseline.json
?? docs/.phase11_npm_audit.json
?? docs/.phase11_python_advisories.json
?? docs/.phase11_python_advisories_after.json
?? docs/.phase11_secret_scan.json
?? docs/.phase11_secret_scan_revalidated.json
?? docs/.phase11_test_runtime/
?? docs/final_security_sovereignty_audit.json
?? docs/final_security_sovereignty_audit.md
```
