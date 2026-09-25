# Advanced-C product integration

Advanced-C adds local voice adapters, a multilingual interface shell, stored-data
BI and optional n8n summary workflows. LangGraph, retrieval, preflight, approval
and evidence governance remain the reasoning and authority boundaries. No hosted
AI, speech or translation dependency is added. No models download automatically.

## Local voice

```text
Local microphone/file → FastAPI STT adapter → editable transcript
→ explicit Submit → existing /query → preflight → existing routing/governance
→ displayed response → optional explicit local TTS playback
```

The browser uses MediaRecorder, not browser speech recognition or OS/network
speech synthesis. Recording stops at 30 seconds and microphone tracks are released.
Local audio files are also accepted. Both input and generated audio are limited
to 4 MiB; adapter HTTP responses are capped at 6 MiB. Supported MIME types are
audio/wav, audio/webm, audio/ogg, audio/mpeg and audio/mp4. Adapter runtime support
for a particular encoding/language is deployment-specific.

Configure independent HTTP adapter URLs; any locally installed engine can supply
these small contracts. The workbench does not assume one model's CLI, SDK or
vendor protocol. An operator-supplied bridge is needed if the chosen runtime has
a different API.

| Operation | Request to configured endpoint | Expected JSON response |
| --- | --- | --- |
| STT | `audio_base64`, `mime_type`, `language` | `{"text":"original transcript"}` |
| TTS | `text`, `language` | `{"audio_base64":"...","mime_type":"audio/wav"}` |

Missing, misconfigured, unreachable or malformed adapters return `unavailable`.
The UI remains functional in text mode; a configured endpoint is explicitly
`configured_unverified`, not a claim that a model is installed or healthy.
Network timeouts are bounded and no automatic retries duplicate submissions.
Transcripts are never automatically submitted. The user must check names,
equipment tags, negations and numbers before submitting.

TTS reads a response's plain-text answer, summary or reason only on request, and
prefixes an advisory/no-operation-permission warning. Structured results without
plain explanatory text remain text-only. Speech is not an approval credential;
spoken technical identifiers may be ambiguous and must be checked against text.

### Locality and retention

Public speech endpoints are rejected. Existing locality classification and DNS
checks require loopback/private resolution. HTTP redirects and environment
proxies are disabled. A configured public speech endpoint invalidates the
sovereignty proof; permitted speech dispatches enter existing process counters.
These are application checks, not firewall enforcement or protection against
DNS rebinding between validation and connection. Deploy adapters without internet
egress and use TLS/network access controls for on-premise LAN endpoints.

Raw audio is held transiently in browser/backend memory and is not written to
database, files or audit events. Responses are `Cache-Control: no-store`.
Configure the adapter and reverse proxy to avoid audio/request-body logging.
Submitted transcripts are ordinary query text: existing trace settings apply,
and governed proposals retain the text needed by the immutable review ledger.
Disabling trace-query storage does not remove required governance records.

## Language support

The language selector supports English, Hindi and Tamil, stored locally in the
browser. Navigation, query controls, operational tabs, voice availability and key
integration/safety labels use curated dictionaries. This is initial interface
localization, not complete translation of every existing field/help message.
Missing labels use English. Unsupported UI language codes fall back to English.

`/query` accepts `input_language` (default `en`) and `input_channel` (`text` or
`voice`). Metadata does not change query content, evidence, prompts, route
authority or technical identifiers. Language-region metadata such as `hi-IN`
is normalized for speech capability handling; unknown languages use `und` while
preserving the originally requested code and text. Existing query request hashes
remain unchanged for default English text; nondefault metadata binds governed
replays so it cannot be silently changed under the same request ID.

There is no automatic translation engine in this delivery. Original input,
output and evidence quotations are retained. Local-model comprehension and
English-centric retrieval/safety-language coverage are not certified for Hindi
or Tamil. Existing preflight can ask for clarification; the UI does not present
translated text as a verified equivalent. Technical strings such as P-204A,
XV-2040, SOP IDs and document identifiers are never dictionary-translated.

## Industrial BI and metric sources

The reviewer/admin-only BI endpoint reads existing local tables. Database errors
remain errors; the frontend does not substitute fabricated zeroes.

| Metric | Source and meaning |
| --- | --- |
| Recorded incidents | Count of IncidentReport rows; open count is unknown because there is no closure-status field |
| Pending human approvals | ActionRevision rows without terminal APPROVE/REJECT decisions; expired approvals are not reclassified as pending |
| Operator notes | Count of OperatorNote rows |
| Generated handovers | HANDOVER_GENERATED audit-event count, excluding note-review runs |
| Environmental assessments | COMPLIANCE_ASSESSMENT_GENERATED event count, not compliance certifications |
| Maintenance advisory revisions | ActionRevision joined to maintenance/combined route runs, including unapproved drafts |
| Knowledge gaps | Distinct observed gap IDs in sampled execution metadata; no automatic resolution inferred |
| Sufficiency / path distributions | Stored execution metadata, with UNKNOWN for missing fields |
| Latency | Means of recorded query latency and generation latency for runs with recorded model calls |
| Model/runtime labels | Stored run configuration; not proof of inference on every run |
| Recent audit activity | Latest 20 event types, times and sequences; no raw audit payloads or credentials |

JSON aggregation uses the latest 1,000 runs; the response exposes sample limit,
sample size, metadata coverage, timestamp and BI query latency. Record, approval,
generated-event and advisory-revision counts are all-time database counts.
Missing latency/gap coverage is null and displayed as Unavailable. Dashboards
neither close incidents nor approve maintenance, compliance or equipment actions.

## Optional n8n integration

LangGraph handles reasoning/decision orchestration. n8n handles scheduling,
movement and operator-configured notification delivery. The new webhook executes
no graph, model, approval, plant write, arbitrary URL or arbitrary query.

Import `infra/n8n/05-wb-operational-summary.json` into a self-hosted n8n instance.
It is inactive by default. The schedule signs a summary request and POSTs it to
the workbench. The template uses the existing repository's Schedule/Code/HTTP
node patterns. Its Code node requires access to the Node crypto builtin and the
listed environment variables; enable those narrowly according to the installed
n8n/task-runner policy. Native n8n import/execution has not been tested here.

Supported `kind` values:

- `shift_handover_reminder`
- `knowledge_gap_notification`
- `pending_review_notification`
- `environmental_review_reminder`
- `maintenance_advisory_notification`
- `report_delivery`
- `audit_summary`

Each returns an advisory BI summary envelope for the scheduler to use. They do
not create a handover or a new assessment. The template deliberately ends at
the response: attach an operator-reviewed local notification/report destination
to perform delivery. No notifications are sent by this implementation. The
response explicitly reports `delivery_performed: false`. Receiver-side delivery
idempotency should use the returned nonce; backend replay prevention cannot
provide exactly-once behavior in an external notification system.

### Authentication and replay

The webhook body contains only `timestamp` (integer Unix seconds), `nonce`
(UUID) and allowlisted `kind`. Supply `X-Workbench-Signature`, the lowercase hex
HMAC-SHA256 of UTF-8 `timestamp.nonce.kind`, using the configured secret.
Extra fields are rejected. A five-minute clock window rejects stale/future
requests. The nonce primary key persists across workers/restarts and rejects
replay, including concurrently repeated requests. Receipt insertion and the
acceptance audit event commit atomically; failed summary generation rolls back.

The configured principal must still exist with reviewer/admin role at each
request. The HMAC credential grants only this summary endpoint; it is not a
session cookie and is not accepted by query/approval/admin APIs. n8n receives no
reviewer password, user UUID, database credentials or ability to issue decisions.
Revoking the configured role or clearing/rotating the secret disables its access.

Keep the secret in deployment secret storage/environment, never workflow JSON.
Template execution-data retention is disabled; the workbench stores nonce/kind
and sanitized audit metadata, not secrets/signatures. Protect the endpoint with
deployment request-size/rate limits and TLS where it crosses a host boundary.
Invalid signatures are rejected without granting an identity or creating a
receipt; accepted webhook events are audited. No SCADA/DCS workflow exists.

## Configuration and APIs

Backend environment (also listed in `.env.example`):

```dotenv
WORKBENCH_STT_URL=
WORKBENCH_TTS_URL=
WORKBENCH_SPEECH_TIMEOUT_SECONDS=30
WORKBENCH_AUTOMATION_SECRET=
WORKBENCH_AUTOMATION_USER_ID=
```

Leave URLs/secret empty for text-only operation with automation disabled.
Set URLs to the exact locally hosted bridge endpoints. Use a high-entropy random
secret of at least 32 characters and an existing reviewer/admin UUID. The UUID
is backend-only. n8n needs `WORKBENCH_BASE_URL`, the same
`WORKBENCH_AUTOMATION_SECRET`, and optional `WORKBENCH_AUTOMATION_KIND` (defaults
to `audit_summary`). The template rejects public/credential-bearing URLs and
disables redirects. Its hostname check is not DNS/firewall attestation.

| Endpoint | Access |
| --- | --- |
| GET /product/status | Authenticated requester/reviewer/admin; sanitized configuration status |
| POST /voice/transcribe | Same authenticated human roles; bounded audio JSON |
| POST /voice/synthesize | Same authenticated human roles; bounded text JSON |
| GET /bi/operational | Reviewer/admin |
| POST /automation/webhook | Valid HMAC, fresh timestamp, unused nonce and current configured reviewer/admin principal |
| POST /query | Existing path, with additive input metadata; voice explicitly requires authentication before replay |

Apply migration `0014_product_integration` after Advanced-B. It adds durable
automation receipts and one structured audit vocabulary entry. Downgrade is
allowed only without integration receipts/events; it refuses to destroy replay
or immutable audit history. Validation uses isolated schemas, not deployment.

STT/TTS usage, language, outcome and latency and BI/webhook events use
PRODUCT_INTEGRATION_EVENT. Query language/channel is stored in existing execution
metadata; default trace/governance persistence behavior remains. No hidden
chain-of-thought, raw audio, transcript content or TTS text enters these new
integration audit events.

## Delivery limits

No speech models/bridges were installed or downloaded, and no live speech accuracy
or multilingual safety-quality claim is made. Text fallback is always available.
Localization is partial and original evidence remains authoritative. BI uses
stored records with explicit sampling and unknown states. Workflow delivery
requires an operator-configured local destination. No new authority, automatic
approval, incident closure or plant-control behavior is introduced.
