# Advanced-C validation

## Recovered state

Recovered at HEAD `25bf2de` (Advanced-B). Ran status, last eight commits,
diff check and diff statistics before edits. Initial tracked changes were the
dataset-license additions and existing Workspace component/test changes (three
files, 31 insertions, two deletions). Several required Advanced-B service files
remained untracked despite the B commit; they were retained and reused.

Preserved `.codex/`, incoming Phase 10 bundle, `claudex-loop/`, Phase 9
seed/validation scripts/tests, dataset-license additions, and pre-existing
Workspace timeout/evidence changes. No reset, checkout, clean or commit was used.

Inspected frontend/App/Operational Workspace, FastAPI dependencies/query routes,
LangGraph routing, governance and immutable request binding, audit chain,
observability, locality checks, existing BI source tables and n8n templates.
No new package or model was installed. Existing routing/prompt architecture stays
in place; optional adapters use the already-installed HTTP client.

## Implemented

- Configurable local STT/TTS HTTP contracts, bounded in-memory audio, manual
  transcript confirmation, normal query submission and optional local playback.
- English/Hindi/Tamil curated UI shell labels, saved language selector and
  additive input language/channel metadata. Original technical text is preserved.
- Reviewer/admin operational BI with real record/audit counts, sampled
  observability distributions, latency and explicit unknown incident status.
- Optional signed summary-only webhook, role revalidation, timestamp window,
  durable nonce replay rejection and inactive n8n schedule template.
- Sanitized integration events, speech-aware sovereignty classification and
  additive execution language metadata. No audio or hidden reasoning storage.

## Targeted backend and P-204

From `backend/`:

```powershell
$env:PYTHONPATH='tests'
.venv/Scripts/python.exe -m unittest test_advanced_c test_phase9 -q
```

**45 passed**, 6.684 seconds: 25 Advanced-C tests plus 20 existing P-204/Phase 9
tests. Local log: `advanced-c-targeted-final.log` (ignored artifact).

Coverage: text operation without speech, unavailable/broken STT/TTS, invalid
audio, original transcript/identifier preservation, confirmation requirement,
advisory TTS prefix, cloud adapter rejection, authenticated voice submission,
preflight refusal without graph execution, mandatory HITL, replay authentication,
language fallback/binding, unknown BI data, stored incident/note/review counts,
actual generated-assessment event counts, execution distributions, BI RBAC,
valid/invalid/expired/tampered/replayed webhook requests, disabled automation,
role revocation, prohibited fields/actions, no approval side effects, no bearer
credential reuse as a human session and speech locality in sovereignty proof.

Tests use controlled adapter/model responses and real SQLite governance/audit
fixtures. P-204 continues through existing controlled evidence, citation and
approval/release/revocation regression tests. No live speech/model accuracy test
or new P-204 model inference was performed.

## Full backend and migration validation

```powershell
$env:PYTHONPATH='tests'
$env:WORKBENCH_TEST_POSTGRES='1'
.venv/Scripts/python.exe -m unittest discover -s tests -q
```

**691 tests run: 690 passed, 1 skipped**, 86.892 seconds. No errors or failures.
The skipped check is opt-in live-model inference. Final local log:
`advanced-c-backend-verified.log` (ignored artifact). PostgreSQL migration
upgrades/downgrades, schema-drift, immutable ledger, concurrency, approval,
audit and security regression checks passed. Initial full runs caught four
existing migration round-trip tests rejecting the initial always-blocked
downgrade. The migration now permits unused-schema downgrade, retains its
history-preservation guard and uses the existing constraint naming convention.

The focused PostgreSQL migration round-trip/schema-drift test passed:

```powershell
.venv/Scripts/python.exe -m unittest test_phase5d_postgres.PostgreSQLEvidenceIntegrityTests.test_migration_downgrade_upgrade_and_metadata -q
```

**1 passed**, 1.361 seconds, with no new schema upgrade operations detected.
Migration checks use isolated schemas; the application's public schema is not
migrated by this work.

## Frontend

From `frontend/`:

```powershell
node --test --test-concurrency=1 src/services/api.test.js src/WorkspacePages.test.js src/OperationalPages.test.js src/ProductPages.test.js
npm run lint
npm run build
```

**11 tests passed**, lint passed and Vite production build passed. New checks
cover language selection/fallback, English/Hindi/Tamil rendering, identifier and
quotation preservation, voice-unavailable/disabled controls, authentication
messaging, BI unknowns/distributions, automation status/boundary, and n8n template
HMAC construction/public-destination rejection. An initial test expected a raw
underscore in a human-readable metric key; the assertion was corrected to match
the existing DataView formatting.

Frontend checks are pure logic, SSR and API-client tests, not a microphone/browser
walkthrough. Template signing code was executed in a controlled JavaScript VM;
native n8n import/scheduler/notification delivery was not run.

## Other validation

- Python compileall of app, migrations and tests passed.
- App import, SQLAlchemy mapper configuration and OpenAPI generation passed:
  **43 paths**.
- `git diff --check` passed; LF/CRLF checkout notices are not failures.
- **101 Phase 10 benchmark files are byte-identical to HEAD**.
- No benchmark truth, validators, prompts or previous results were changed.
- No validation/blind benchmark cases or final model comparison were run.

## Files changed in this session

New backend files:

- `backend/alembic/versions/0014_product_integration.py`
- `backend/app/api/routes/product.py`
- `backend/app/db/models/automation_receipt.py`
- `backend/app/schemas/product.py`
- `backend/app/services/local_voice.py`
- `backend/app/services/industrial_bi.py`
- `backend/app/services/product_integration.py`
- `backend/tests/test_advanced_c.py`

Modified backend/config files: `.env.example`, API router/query route, settings,
model registration/audit vocabulary, query/sovereignty schemas, governance
request metadata binding, execution observability, sovereignty service and
foundation metadata-count expectation.

Frontend: added `ProductPages.jsx`, `ProductPages.test.js`, `language.js`;
updated App navigation/context, OperationalPages tab labels and WorkspacePages
query voice/language controls while preserving recovered changes.

Added `infra/n8n/05-wb-operational-summary.json`,
`docs/advanced-c-product-integration.md` and this validation record.
Unrelated/untracked Advanced-B and Phase 9 files were not rewritten.

## Remaining limits

Speech requires an operator-installed runtime/HTTP bridge; none was installed or
downloaded. Language UI coverage is partial, automatic translation is disabled,
and multilingual retrieval/safety quality is not certified. BI has a latest-1000
run sample and cannot infer incident closure. n8n delivery needs an explicitly
configured local recipient/destination; this implementation sends nothing.
Locality checks are not firewall attestation. Required schema deployment remains
an operator step. All features are advisory; no plant/approval authority added.

Verdict: **ADVANCED-C COMPLETE**. No commit and no final benchmark/model comparison.
