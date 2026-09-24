# Advanced-A1 validation

Result: **ADVANCED-A1 COMPLETE**

## Recovery and scope

Starting HEAD: `39e6d16 Phase 10.3: freeze benchmark interface and development baseline`. The starting working tree contained unrelated changes to the dataset license manifest and two frontend files, plus local tooling/incoming bundle and Phase 9 untracked files. Those were preserved.

All 101 tracked benchmark files were compared byte-for-byte to HEAD after implementation and remain unchanged. No benchmark cases, expected values, validators, prompts, contracts or result files changed. No validation/blind inference, model downloads, commits or Advanced-A2 work occurred.

## Commands and results

Run from backend with `PYTHONPATH=tests` and `WORKBENCH_TEST_POSTGRES=1`:

```powershell
.venv/Scripts/python.exe -m unittest test_advanced_a1 -q
.venv/Scripts/python.exe -m unittest discover -s tests -q
```

- A1 targeted suite: **26 passed**, 7.297 seconds. Includes 25 deterministic service/API checks and one live PostgreSQL registry lifecycle test.
- Full backend suite: **579 run; 578 passed; 1 skipped**, 65.271 seconds, exit 0. The skipped test is the opt-in live-model inference check (`WORKBENCH_TEST_LIVE_MODEL` was not enabled).
- Compile validation: `python -m compileall -q backend/app backend/alembic backend/tests/test_advanced_a1.py` passed.
- `git diff --check` passed. Windows LF-to-CRLF warnings are not failures.
- PostgreSQL migration upgrade and Alembic metadata checks passed in isolated schemas; no new upgrade operations detected.

## Coverage

The focused tests prove candidate/stale/revoked exclusion; verified P-204-style informational hits; existing source and citation identity; local file, chunk content, document version hash/revision/scope and revoked-source invalidation; anonymous/scope exclusion; forged reviewer-role rejection; no model-supplied verification state; self-review denial; exact-match ambiguity fallback; unsafe and non-static query exclusion; existing approval revocation enforcement; immutable proposal binding checks; verification/revocation audit events and chain verification; import trust reset; OCR exclusion; revision linkage; preflight-before-lookup; common governance after a hit; unauthenticated mutation denial; and rollback of both approval and registry promotion if mandatory audit fails.

The live PostgreSQL A1 test migrates an isolated schema, creates source metadata and a candidate, approves/verifies using the existing ledger, serves a trusted match, revokes it, rejects later lookup, and verifies the audit chain. It uses a deterministic Qdrant response fixture and a real temporary local source file. It does not claim a live Qdrant ingestion, frontend, or live-model end-to-end test. Existing PostgreSQL security/approval/evidence tests also pass in the full suite.

Initial validation caught and repaired the missing knowledge-event audit allowlist, the expected metadata table count (23 to 24), and a governed-response replay difference caused by additional metadata. The final suite verifies those repairs. The source gate additionally requires PostgreSQL version scope and snapshots all version metadata; the static fast-path grammar excludes advisory/safety scenarios.

## Deployment and limits

The migration is delivered and validated; this task did not migrate the application's operational schema. Apply Alembic upgrade head when deploying A1. Until then, query lookup fails closed to the existing path; registry APIs require the new table.

Only authenticated internal-scope non-OCR document knowledge qualifies. Source PDFs must remain under data_root. No registry-specific frontend is added; backend APIs and the existing approval queue supply the workflow. A1 uses lazy deterministic invalidation before inspection or serving, not a background invalidation worker. Source checks are snapshots across PostgreSQL/Qdrant/local files, not a distributed transaction. Existing human approval expiry/revocation remains authoritative.

The representation is explicitly an application-owned **OKF-compatible adapter/representation layer**, adapter version `a1-v1`; no external specification or certified compliance is claimed. Human review and content hashes do not prove current plant state, OCR isolation, or semantic truth.

## Intentional files

Added:
- backend/alembic/versions/0011_verified_knowledge.py
- backend/app/db/models/verified_knowledge.py
- backend/app/schemas/verified_knowledge.py
- backend/app/services/verified_knowledge.py
- backend/app/api/routes/verified_knowledge.py
- backend/tests/test_advanced_a1.py
- docs/advanced-a1-verified-knowledge.md
- docs/advanced-a1-validation.md

Modified:
- backend/app/db/models/__init__.py (register model)
- backend/app/db/models/audit_event.py (knowledge-event vocabulary)
- backend/app/api/router.py (register authenticated routes)
- backend/app/api/routes/query.py (post-preflight lookup and observability)
- backend/app/schemas/query.py (optional informational lookup metadata)
- backend/tests/test_foundation.py (24-table schema expectation)
