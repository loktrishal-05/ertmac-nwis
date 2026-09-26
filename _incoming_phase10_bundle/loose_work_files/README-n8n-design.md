# Self-hosted n8n workflows for the Sovereign On-Premise Agentic AI Workbench

**Project:** SIH26117 — Sovereign On-Premise Agentic AI Workbench (MRPL)
**Scope of this document:** peripheral workflow automation only. Design/support work.
**Status of the AI core:** unchanged. LangGraph remains the orchestrator.

---

## 1. Architecture explanation

### 1.1 The two layers, and why they are not the same thing

```
React → FastAPI → LangGraph → {Orchestrator, Knowledge, Safety, Maintenance,
                               Process-Optimisation} → Guardrail → Human Approval
                            → local open-weight LLMs
```

That is the **AI core**. It reasons, routes, retrieves, cites, scores confidence, and
gates everything action-adjacent behind a human. Nothing below changes any of it.

n8n sits **beside** that stack as a **peripheral automation layer**. It is a scheduler,
an HTTP client, a file mover and a notifier. Concretely, in this design n8n:

- never classifies intent or routes a request to an agent;
- never calls an LLM, an embedding model, a reranker or an OCR engine directly;
- never constructs, edits or ranks evidence, citations or recommendations;
- never approves, rejects, escalates-to-approved, or closes an approval;
- never writes to SCADA/DCS or anything that affects plant state.

The one-line version for a judge or a reviewer:

> **LangGraph decides. n8n fetches, schedules, files and tells a human. If you deleted
> n8n entirely, the workbench would still answer questions, still guardrail them, and
> still require human approval — you would just lose a scheduler and a notifier.**

### 1.2 The trust boundary

n8n is on the **advisory/IT side** of the boundary, and it talks to the workbench only
through the workbench's own HTTP API — the same public surface the React dashboard uses.
It has no database credentials, no Qdrant write access, no model-server access beyond a
read-only model *listing*, and no shell on the backend container.

This matters for §19 of the Master Report (IT/OT segmentation): adding n8n must not add
a new path toward control systems. It does not, because n8n's entire vocabulary is
`GET`/`POST` against the workbench API plus append-only file writes to a dedicated
volume.

### 1.3 The four standing rules encoded in every workflow

| # | Rule | How it is enforced, not just stated |
|---|---|---|
| R1 | n8n never approves anything | WB-02's queue call is a `GET`; a Code node asserts the method is `GET` and aborts otherwise. The only `POST` back to `/approvals/...` is a *delivery receipt* sub-resource — off by default (`WB_APPROVAL_RECEIPTS_ENABLED=false`), and carrying no decision field even when on. |
| R2 | n8n never touches plant state | No SCADA/DCS/Modbus/OPC node exists in any workflow. n8n's container has no route to the control network. `N8N_DISABLE_NODES` blocks shell/SSH-class nodes. |
| R3 | Retrieved content is data, never instructions | WB-02 scans the approval payload for action/approval directives (`auto_approve`, `bypass_loto`, `stop_pump`, …) and aborts the tick rather than relaying a payload that is trying to steer the automation. |
| R4 | Audit history is append-only | WB-04 writes with `append: true` only, names each manifest uniquely per run, and refuses to advance its cursor across a hash-chain discontinuity. No workflow has a delete node. |

### 1.4 Architecture diagram

See `architecture-langgraph-vs-n8n.mermaid` (renders in any Mermaid viewer, GitHub, or
the n8n docs site). The dashed red edges are the explicit prohibitions — they are drawn
on purpose so that the diagram states what n8n *cannot* do, not only what it does.

---

## 2. Endpoint inventory — what actually exists today

This is the part that decides what can be built now. Status is taken from your own
Phase 3A / 3B1 / 3B2 guides and the Master Report §17, not assumed.

| Endpoint | Status | Evidence / caveat |
|---|---|---|
| `GET /health` | **IMPLEMENTED** | README: returns `{"status":"ok","service":"sovereign-agentic-workbench-backend"}` |
| `POST /documents/ingest` | **IMPLEMENTED** | Phase 3A. Path-based (`source_path` under `data/raw`), **not** a file upload. SHA-256 dedup, 409 on metadata conflict. |
| `POST /documents/pid/process` | **IMPLEMENTED** | Phase 3B1. `source_path` relative to `data/raw/pids/source/`. |
| `POST /documents/pid/{version_id}/index` | **IMPLEMENTED** | Phase 3B2. |
| `POST /knowledge/retrieve` | **IMPLEMENTED** | Phase 3B2. Not used by these workflows — retrieval belongs to the agents. |
| `GET /sovereignty/proof` | **IMPLEMENTED, BUT STATIC** | Phase 3A guide: "remains the Phase 2 static declaration, not network attestation or a measured outbound-call counter." WB-03 therefore labels it `declared`, never `ok`. |
| `POST /query` | **ROUTE EXISTS, CONTRACT UNSPECIFIED** | Master Report §17; Phase 3B1 says the query contract is preserved. Field-level schema is not in the supplied documents. Not used by any workflow here. |
| `GET /agents/status` | **ROUTE EXISTS, CONTRACT UNSPECIFIED** | Same as above. |
| `GET /approvals` | **ROUTE EXISTS, BEHAVIOUR ABSENT** | README (current phase): "approval workflow … absent". WB-02 handles `404`/`501` gracefully and exits quietly rather than reporting a healthy empty queue. |
| `GET /audit/log` | **ROUTE EXISTS, BEHAVIOUR ABSENT** | README: "audit hash chaining … absent". WB-04 is written against the §16 `AuditLog` schema and degrades to `not_implemented`. |

### 2.1 Explicitly **FUTURE API REQUIRED**

None of the following exist. Each is marked in the workflow JSON on the node that would
call it, and each workflow runs correctly without it.

| Needed by | Endpoint | Purpose |
|---|---|---|
| WB-02 | `GET /approvals?status=pending&limit=N` | Server-side filtering of the queue. Today n8n filters client-side. |
| WB-02 | `POST /approvals/{id}/notifications` | Record that a notification was delivered. **Receipt only — must never accept a decision field.** |
| WB-03, WB-04 | `GET /audit/verify` | Server-side hash-chain verification. |
| WB-04 | `GET /audit/log?cursor=&limit=&order=` | Stable cursor pagination over an append-only log. |
| WB-03 | `GET /knowledge/stats` | Document-level indexed count. Today WB-03 reads Qdrant's own `points_count`, which counts **chunks, not documents**. |
| WB-03 | `GET /models/status` | Workbench-level view of loaded local models. Today WB-03 reads the local Ollama `/api/tags`. |
| WB-02 | outbound event emitter → n8n webhook | Would replace polling. The disabled `Webhook: Approval Created` node is the landing point. |
| all | Bearer-token auth on the API | Phase 3B2: "Authentication/RBAC is still absent." Workflows already send the header so nothing changes when auth lands. |

> **Response shapes in this document are illustrative.** The Phase guides describe the
> *fields* returned (IDs, checksum, status, warnings, counts) but not their exact JSON
> key names. Before going live, diff every payload against the live OpenAPI schema at
> `GET /openapi.json` (FastAPI serves it automatically) and adjust the Code nodes' field
> lookups. Each Code node already reads several plausible aliases for this reason.

---

## 3. Credentials and environment variables

### 3.1 The split: secrets in credentials, configuration in `$env`

Do not put the API token in `$env`. `$env` is readable by anyone who can open a
workflow in the n8n editor, and `N8N_BLOCK_ENV_ACCESS_IN_NODE` defaults to `false`
(i.e. expressions *can* read the environment). Secrets belong in n8n credentials, which
are encrypted at rest with `N8N_ENCRYPTION_KEY` and are not readable from expressions.

**n8n credentials to create (Header Auth type):**

| Credential name | Type | Header | Used by |
|---|---|---|---|
| `Workbench API Token` | Header Auth | `Authorization: Bearer <token>` | WB-01, WB-02, WB-03, WB-04 |
| `n8n Inbound Webhook Token` | Header Auth | `X-Workbench-Token: <token>` | WB-02 future webhook only |

In the JSON files each credential reference is `"id": "REPLACE_WITH_CREDENTIAL_ID"` —
n8n rebinds it by *name* on import, so you only need to create the credential once.

### 3.2 Environment variables (non-secret configuration)

```dotenv
# --- workbench ---
WORKBENCH_BASE_URL=http://backend:8000
WORKBENCH_UI_BASE_URL=https://workbench.internal.mrpl

# --- notification (URLs may themselves be sensitive; see §3.3) ---
INTERNAL_NOTIFICATION_WEBHOOK=http://notify.internal:8080/hooks/workbench-ops
INTERNAL_ESCALATION_WEBHOOK=http://notify.internal:8080/hooks/workbench-escalation

# --- local infrastructure (read-only probes) ---
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=knowledge_chunks_v1
OLLAMA_BASE_URL=http://ollama:11434

# --- filesystem ---
WB_DATA_ROOT=/data/raw
WB_WATCH_GLOB=/data/raw/**/source/*.pdf
WB_LOG_DIR=/data/n8n/logs
WB_REPORT_DIR=/data/n8n/reports/sovereignty
WB_AUDIT_EXPORT_DIR=/data/n8n/archive/audit

# --- behaviour ---
WB_FACILITY_ID=prototype
WB_PID_AUTO_INDEX=false
WB_APPROVAL_RENOTIFY_MINUTES=30
WB_APPROVAL_MAX_REMINDERS=3
WB_APPROVAL_RECEIPTS_ENABLED=false
WB_AUDIT_PAGE_SIZE=500
WB_AUDIT_MAX_PAGES=200

# --- n8n hardening ---
N8N_ENCRYPTION_KEY=<generate once, back up, never commit>
N8N_RESTRICT_FILE_ACCESS_TO=/data/raw:/data/n8n
N8N_BLOCK_FILE_ACCESS_TO_N8N_FILES=true
N8N_DISABLE_NODES=n8n-nodes-base.executeCommand,n8n-nodes-base.ssh,n8n-nodes-base.executeWorkflowTrigger
N8N_DIAGNOSTICS_ENABLED=false
N8N_VERSION_NOTIFICATIONS_ENABLED=false
N8N_TEMPLATES_ENABLED=false
N8N_PERSONALIZATION_ENABLED=false
EXECUTIONS_DATA_PRUNE=true
EXECUTIONS_DATA_MAX_AGE=336
GENERIC_TIMEZONE=Asia/Kolkata
```

Nothing above is a secret except `N8N_ENCRYPTION_KEY` and the two webhook URLs, which
should come from Docker secrets or an env file with `0600` permissions — never from the
repository.

> **n8n 2.0 note.** From n8n 2.0, `N8N_RESTRICT_FILE_ACCESS_TO` defaults to `~/.n8n-files`
> unless set explicitly, and the Local File Trigger node is disabled by default in
> untrusted environments. This design is unaffected: it sets the variable explicitly and
> uses a Schedule Trigger + Read/Write Files, not a filesystem watcher.

### 3.3 Deployment sketch

```yaml
# infra/docker-compose.n8n.yml — joins the existing internal network, adds no egress
services:
  n8n:
    image: docker.n8n.io/n8nio/n8n:latest      # pin an exact tag in production
    restart: unless-stopped
    env_file: [./n8n.env]
    networks: [workbench_internal]             # internal: true — no route to the internet
    ports: ["127.0.0.1:5678:5678"]             # loopback only; reach it via the internal proxy
    volumes:
      - n8n_data:/home/node/.n8n
      - ../data/raw:/data/raw:ro               # READ-ONLY: n8n must never mutate the corpus
      - n8n_out:/data/n8n                      # logs, reports, audit archive
    depends_on: [backend]

networks:
  workbench_internal:
    internal: true                             # the sovereignty control that actually holds

volumes:
  n8n_data:
  n8n_out:
```

Two deliberate choices: `data/raw` is mounted **read-only** (n8n reads filenames and
hands the API a path; it never rewrites a source document), and the network is
`internal: true` so the "no external AI calls" claim is enforced by Docker, not by
workflow discipline — consistent with Master Report §7: *"enforced by infrastructure,
not by application code that could be bypassed."*

---

## 4. WB-01 — Scheduled document ingestion

**File:** `01-wb-scheduled-document-ingestion.json`
**Trigger:** every 15 minutes
**Purpose:** pick up new SOPs / incident reports / manuals / P&IDs from the approved
local folder and submit them to the workbench ingestion API.

### 4.1 The design decision that matters

Phase 3A's ingestion API is **path-based**, not an upload:
`{"source_path": "sops/source/example.pdf", ...}`. So the correct pattern is:

> **The document bytes never travel over HTTP at all.** n8n and the backend share the
> same `data/raw` volume; n8n sends a *relative path* plus metadata, and the backend
> reads the file from disk itself.

This is a sovereignty win worth stating out loud in the demo: adding a workflow engine
did not create a second copy of confidential SOPs, and did not put document content on
the wire.

The second decision: **idempotency is owned by the backend.** Phase 3A returns the
original IDs with status `duplicate` and performs no re-embedding for identical bytes +
metadata. So re-running the workflow is always safe, and n8n's local cache is a
bandwidth optimisation that can be wiped at any time without consequence.

### 4.2 Node-by-node

| # | Node | Type | Input | Output |
|---|---|---|---|---|
| 1 | Every 15 Minutes | Schedule Trigger | — | `{}` (tick) |
| 2 | Set: Run Context | Set | tick | `run_id`, `started_at`, `workbench_base_url`, `data_root`, `watch_glob`, `facility_id`, `pid_auto_index` |
| 3 | Read Watch Folder | Read/Write Files (read) | glob from ctx | one item per file: `binary.data` + `{fileName, directory, fileExtension, fileSize, mimeType}`. Error output → node 18 |
| 4 | Code: Validate And Plan | Code | file items | per file: `{decision: submit\|skip, reason?, rel_path, is_pid, document_type, ingest_body, cache_key}` |
| 5 | Filter: Submittable | Filter | planned items | only `decision == 'submit'` |
| 6 | Loop Over Files | Split In Batches (1) | submittable | out 0 = done → node 15; out 1 = one file → node 7 |
| 7 | If: Is P&ID Drawing | If | one file | true → node 8; false → node 11 |
| 8 | HTTP: Process P&ID | HTTP Request | `ingest_body` | `{statusCode, body}`; error output → node 13 |
| 9 | If: Auto-Index P&ID | If | P&ID result | true → node 10; false → node 13 |
| 10 | HTTP: Index P&ID Regions | HTTP Request | `document_version_id` | `{statusCode, body}` → node 13 |
| 11 | HTTP: Ingest Document | HTTP Request | `ingest_body` | `{statusCode, body}`; error output → node 13 |
| 12 | *(reserved)* | — | — | — |
| 13 | Code: Record Outcome | Code | HTTP result | `{outcome, retryable, http_status, document_id, document_version_id, sha256, warnings}`; loops back to node 6 |
| 14 | *(loop edge)* | — | — | — |
| 15 | Code: Summarise Run | Code | all outcomes | run tally + NDJSON blob |
| 16 | Append Ingest Log | Read/Write Files (write, append) | NDJSON | appended to `ingest-YYYY-MM-DD.jsonl` |
| 17 | If: Any Failures | If | summary | true → node 18; false → Run Complete |
| 18 | Notify Ingest Failures | HTTP Request | summary | POST to `INTERNAL_NOTIFICATION_WEBHOOK` |
| 19 | Notify Scan Failure → Stop | HTTP + Stop and Error | scan error | notifies, then fails the run into WB-00 |

### 4.3 Validation rules applied in node 4

| Check | Rejection reason | Why |
|---|---|---|
| directory metadata present | `directory_metadata_missing` | never guess a path — a wrong `source_path` ingests the wrong file |
| path under `WB_DATA_ROOT` | `path_outside_data_root` | traversal guard |
| filename `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` | `filename_not_allowlisted` | blocks spaces, quotes, Windows ADS `:`, unicode look-alikes |
| extension in `pdf/png/jpg/jpeg` | `extension_not_allowed:<ext>` | matches what the API accepts |
| size ≤ 20 MiB | `exceeds_20MiB_api_limit` | Phase 3A/3B1 hard limit — fail here, not with a 4xx |
| subfolder maps to a `document_type` | `unmapped_subdirectory` | `sops/ → sop`, `incidents/ → incident`, `manuals/ → manual`, `pids/ → pid` |
| text corpus is PDF | `text_corpus_requires_pdf` | Phase 3A is PDF-only |
| P&ID under `pids/source/` | `pid_must_live_under_pids_source` | Phase 3B1 accepts nothing else |
| not already submitted | `already_submitted_this_instance` | local cache; backend still de-duplicates |

Note the 100-page limit and the English-language restriction are **not** pre-checked —
n8n cannot see inside the PDF without parsing it, which would duplicate Docling's job.
Those surface as a `4xx` and are logged as `rejected`.

### 4.4 Example payloads and responses

**Request — text document**

```http
POST /documents/ingest HTTP/1.1
Host: backend:8000
Content-Type: application/json
Authorization: Bearer <from n8n credential>
```
```json
{
  "source_path": "sops/source/SOP-P204-001.pdf",
  "title": "SOP-P204-001",
  "document_type": "sop",
  "revision": "unspecified",
  "facility_id": "prototype",
  "synthetic": false,
  "access_scope": "internal"
}
```

**Response — first ingestion (illustrative shape)**

```json
{
  "document_id": "3f6b1c2e-7a41-4f0e-9c3d-1b2a5c6d7e8f",
  "document_version_id": "8c1d4e5f-2b73-4a19-9d6c-0e7f8a9b1c2d",
  "status": "indexed",
  "checksum_sha256": "9f2c...b71a",
  "chunks_indexed": 42,
  "warnings": []
}
```

**Response — identical bytes resubmitted**

```json
{
  "document_id": "3f6b1c2e-7a41-4f0e-9c3d-1b2a5c6d7e8f",
  "document_version_id": "8c1d4e5f-2b73-4a19-9d6c-0e7f8a9b1c2d",
  "status": "duplicate",
  "checksum_sha256": "9f2c...b71a",
  "warnings": ["source already ingested; no re-embedding performed"]
}
```

**Response — conflicting metadata for the same checksum**

```json
{ "detail": "Checksum already registered with different metadata" }
```
→ HTTP `409` → outcome `conflict`, `retryable: false`, notified, cached so it is not
retried in a loop.

**Request — P&ID drawing**

```json
{
  "source_path": "TEP-100-PID-001.pdf",
  "title": "TEP-100-PID-001",
  "revision": "unspecified",
  "synthetic": false,
  "render_dpi": 300,
  "preprocessing": {
    "grayscale": true,
    "contrast_normalization": true,
    "adaptive_threshold": false,
    "denoise": false,
    "rotation_degrees": 0
  }
}
```

Defaults deliberately avoid thresholding and denoising, per the Phase 3B1 warning that
they can erase thin text strokes.

### 4.5 Error-handling route and retry behaviour

| Failure | Detection | Route | Retry |
|---|---|---|---|
| Watch folder unreadable | node 3 error output | notify → `Stop and Error` → WB-00 | none (config problem, not transient) |
| Ingest HTTP `5xx` | `statusCode >= 500` | outcome `server_error`, `retryable: true`, **not cached** | node-level: 3 tries, 20 s apart; then next 15-min tick |
| Connection reset / timeout | HTTP node error output | outcome `transport_error`, not cached | same |
| `409` conflict | `statusCode == 409` | outcome `conflict`, cached | none — human must resolve the metadata |
| `4xx` reject | `400 ≤ status < 500` | outcome `rejected`, cached | none |
| Duplicate | `body.status == 'duplicate'` | outcome `duplicate`, cached | none — success |
| Log write fails | `onError: continueRegularOutput` | run continues, notification still sent | none |
| Workflow itself throws | n8n `errorWorkflow` | WB-00 | n8n manual retry from the executions list |

`neverError: true` + `fullResponse: true` on every HTTP node is the key trick: the node
returns the status code as data instead of throwing, so a `409` is *classified* rather
than turned into an opaque workflow crash. Genuine transport failures still take the
error output.

`Loop Over Files` with `batchSize: 1` is deliberate — Phase 3A ingestion is synchronous
and CPU-bound (Docling + BGE on CPU), so concurrency would only cause timeouts.
Timeouts are set to 900 s for the same reason.

---

## 5. WB-02 — Human-approval notification (read-only)

**File:** `02-wb-approval-notification.json`
**Trigger:** every 5 minutes (poll). A disabled Webhook node marks the future push path.
**Purpose:** tell an authorised engineer that an approval is waiting. Nothing else.

### 5.1 Three design decisions

**(a) Polling, because the backend has no event emitter.** The Master Report describes
an approval queue but nothing that calls out to a subscriber. `Webhook: Approval Created`
exists in the JSON, disabled, wired to the same downstream path, so switching to push
later is a one-click change plus one FUTURE endpoint.

**(b) The notification is redacted by design.** Approval drafts can quote Confidential or
Restricted SOP and incident text (§10 classification tiers; §19 DLP on export paths). A
chat or e-mail channel is an export path with no RBAC. So the message carries **only**:

| Sent | Withheld |
|---|---|
| `approval_id`, `asset_tag`, `action_class`, `risk_level`, requesting agent, waiting time, deep link | `draft_output`, citations, document excerpts, sensor values, incident narrative, requester identity |

The engineer clicks through to the workbench and reads the content there, under the
role-based visibility §10 requires. This turns the notification from a leak vector into
a pointer.

**(c) A hard safety guard, not a comment.** `Code: Safety Guard` asserts the queue call
is a `GET` and aborts if someone later edits it into a write. It also scans the response
for action/approval directives — retrieved content is untrusted data (§19), and an
approval payload that contains `auto_approve` or `bypass_loto` is an injection attempt,
so the tick aborts **without notifying anyone**, and WB-00 escalates.

### 5.2 Node-by-node

| # | Node | Type | Input | Output |
|---|---|---|---|---|
| 1 | Every 5 Minutes | Schedule Trigger | — | tick |
| 1b | Webhook: Approval Created (FUTURE) | Webhook, **disabled** | — | would carry `{approval_id}` |
| 2 | Set: Run Context | Set | tick | URLs, `renotify_after_minutes`, `max_reminders`, `record_delivery_receipts` |
| 3 | HTTP GET: Pending Approvals | HTTP Request (**GET**) | — | `{statusCode, body}`; error output → node 12 |
| 4 | Code: Safety Guard | Code | response | `{queue_available, approvals[]}` or **throws** |
| 5 | Code: Select And Redact | Code | approvals | one redacted item per approval needing notification |
| 6 | Loop Over Approvals | Split In Batches (1) | items | out 0 → node 10; out 1 → node 7 |
| 7 | Notify Authorised Engineer | HTTP Request | redacted item | POST to notification webhook |
| 8 | Code: Record Delivery | Code | delivery result | `{delivered, http_status}`; **only a success updates dedupe state** |
| 9 | If: Receipts Enabled → POST Delivery Receipt (FUTURE) | If + HTTP | — | receipt only; no decision field |
| 10 | Code: Summarise Tick | Code | all deliveries | counts + NDJSON ledger |
| 11 | If: Anything To Log → Append Delivery Ledger → If: Any Delivery Failures → Escalate | If / Files / If / HTTP | — | second-channel escalation |
| 12 | Code: Queue Unreachable → Stop and Error | Code + Stop | error | fails into WB-00 |

### 5.3 Escalation ladder

| Risk level | Channel | Reminder policy |
|---|---|---|
| `low`, `medium`, `unknown` | `sovereign-workbench-approvals` | re-notify after 30 min, max 3 |
| `high`, `critical` | `sovereign-workbench-escalation` | same cadence, different audience |
| delivery itself failed | `INTERNAL_ESCALATION_WEBHOOK` | immediate, after node retries exhaust |

A failed send **never** marks the approval as notified, so it is retried on the next
tick. Silence is the one failure mode that matters here: an approval nobody hears about
is an approval that rots in the queue.

### 5.4 Example payload and response

**Request**
```http
GET /approvals?status=pending&limit=100
```

**Response (illustrative — confirm against `/openapi.json`)**
```json
{
  "items": [
    {
      "id": "ap_01J9Z8Q4N7",
      "status": "pending",
      "action_id": "act_7741",
      "agent_name": "safety_incident_agent",
      "asset_tag": "P-204A",
      "action_class": "isolation",
      "risk_level": "high",
      "created_at": "2026-09-16T04:12:33Z",
      "draft_output": "…Confidential draft text…"
    }
  ],
  "next_cursor": null
}
```

**Outbound notification (note what is absent)**
```json
{
  "channel": "sovereign-workbench-escalation",
  "severity": "high",
  "title": "Approval pending in Sovereign Workbench",
  "approval_id": "ap_01J9Z8Q4N7",
  "asset_tag": "P-204A",
  "action_class": "isolation",
  "risk_level": "high",
  "requesting_agent": "safety_incident_agent",
  "waiting_minutes": 7,
  "review_url": "https://workbench.internal.mrpl/approvals/ap_01J9Z8Q4N7",
  "body": "An AI-drafted recommendation is waiting for authorised human review. Approve or reject INSIDE the Sovereign Workbench. This message is a notification only - replying to it approves nothing.",
  "content_withheld": "Content withheld by design. Open the workbench to review."
}
```

`draft_output` is gone. That is the whole point.

### 5.5 Error handling and retry

| Failure | Route | Retry |
|---|---|---|
| Queue `404`/`501` (not implemented yet) | quiet exit, no notification, no alarm | none |
| Queue `5xx` / unreachable | `Stop and Error` → WB-00 → ops channel | node: 3 tries, 10 s apart |
| Injection directive in payload | `throw` **before** any notification → WB-00 critical path | none — deliberate |
| Notification delivery fails | dedupe state untouched; escalation to second channel | node: 4 tries, 15 s apart, then next tick |
| Receipt POST fails (FUTURE endpoint) | `continueRegularOutput` — never blocks the loop | node: 2 tries |

---

## 6. WB-03 — Daily sovereignty status report

**File:** `03-wb-daily-sovereignty-report.json`
**Trigger:** `0 6 * * *` in `Asia/Kolkata` (set in workflow settings — n8n cron is
evaluated in the workflow/instance timezone).

### 6.1 No AI, deliberately

The requirement says no external AI service may create the report. This design goes
further: **no AI at all, including the local LLM.** A compliance artifact has to be
byte-reproducible from the same probe responses and reviewable line by line. An LLM
summary is neither. `Code: Build Report (no LLM)` is plain deterministic JavaScript.

### 6.2 The honest-status pattern

Every section carries one of four statuses, and the report never dresses a gap as health:

| Status | Meaning |
|---|---|
| `ok` | probe answered, value is trustworthy |
| `declared` | endpoint answered, but the value is a **static declaration**, not a measurement |
| `not_implemented` | endpoint does not exist yet (FUTURE API REQUIRED) |
| `unavailable` | endpoint exists but did not answer |

Three caveats are hard-coded into the output so nobody can quote a number without them:

1. **External AI calls** → `declared`. Phase 3A states `/sovereignty/proof` "remains the
   Phase 2 static declaration, not network attestation or a measured outbound-call
   counter." A zero from that endpoint is an *assertion*, not evidence. The real evidence
   is the `internal: true` Docker network and the DNS/SNI egress block (§7).
2. **Indexed count** → Qdrant's `points_count` counts **chunks, not documents**.
3. **Audit chain** → `not_implemented` today, and the report says "UNVERIFIED, not
   verified-good." Those are different claims and conflating them would be the single
   most misleading thing this report could do.

### 6.3 Node-by-node

| # | Node | Reads | Status handling |
|---|---|---|---|
| 1 | Daily 06:00 IST | — | — |
| 2 | Set: Run Context | env | — |
| 3 | Probe: Sovereignty Proof | `GET /sovereignty/proof` | → `declared` |
| 4 | Probe: Backend Health | `GET /health` | → `ok` / `unavailable` |
| 5 | Probe: Local Models | `GET {OLLAMA_BASE_URL}/api/tags` (local; vLLM: `/v1/models`) | listing only — no inference |
| 6 | Probe: Qdrant Collection | `GET {QDRANT_URL}/collections/{name}` | `points_count` |
| 7 | Probe: Pending Approvals | `GET /approvals?status=pending` | count only |
| 8 | Probe: Audit Chain (FUTURE) | `GET /audit/verify` | → `not_implemented` today |
| 9 | Merge Probes | 6 inputs, append | ensures all probes complete first |
| 10 | Code: Build Report (no LLM) | all | Markdown + JSON |
| 11–12 | Write Markdown / JSON Report | — | `sovereignty-YYYY-MM-DD.{md,json}` — `append: false`, so a same-day re-run *replaces* that day's report. Intentional: a status report is a snapshot, not history. The only append-only artifact in the system is WB-04's audit archive. |
| 13 | Notify Daily Summary | — | one-line digest to ops |

Every probe is `neverError: true`, `alwaysOutputData: true`,
`onError: continueRegularOutput` — one dead dependency must degrade the report, never
cancel it. A report that fails to generate on the day something broke is worse than
useless.

### 6.4 Example output

```json
{
  "report_type": "daily_sovereignty_status",
  "report_date": "2026-09-16",
  "generated_by": "n8n:WB-03 (deterministic, no LLM)",
  "overall": "ok_with_gaps",
  "external_ai_calls": {
    "value": 0,
    "status": "declared",
    "caveat": "Static declaration from the Phase 2 endpoint. NOT a measured egress counter…"
  },
  "local_models": { "status": "ok", "runtime_reachable": true, "model_count": 3 },
  "indexed_documents": { "status": "ok", "points_count": 1284, "caveat": "points_count counts CHUNKS, not documents…" },
  "audit_chain": { "status": "not_implemented", "chain_valid": null, "caveat": "…Chain integrity is UNVERIFIED, not verified-good." },
  "pending_approvals": { "status": "ok", "pending_count": 2 },
  "disclaimer": "Operational status report. It does not certify process safety, does not authorise any plant action…"
}
```

### 6.5 Error handling and retry

| Failure | Route | Retry |
|---|---|---|
| Any single probe fails | section marked `unavailable`, `overall: degraded` | node: 2–3 tries, 5 s apart |
| All probes fail | report still written, every section `unavailable` | as above |
| File write fails | `continueRegularOutput` — notification still sent | none |
| Notification fails | `continueRegularOutput` — report is on disk regardless | node: 3 tries, 15 s apart |

---

## 7. WB-04 — Audit export / archive (append-only)

**File:** `04-wb-audit-export-archive.json`
**Trigger:** `30 2 * * *` IST.

### 7.1 Immutability, enforced four ways

| Mechanism | Implementation |
|---|---|
| Records written verbatim | no field is edited, reordered or dropped in `Code: Build Export` |
| Append-only writes | `Append Audit Archive` uses `options.append: true`. Setting it to `false` would destroy history — the node carries that warning in its `notes`. |
| Manifests never overwritten | filename is `manifest-<ISO timestamp>-<run_id>.json`, unique per run |
| Cursor is a commit point | `Code: Commit Cursor` runs **after** a successful write. A failed write leaves the cursor where it was, so the same range is re-exported next run rather than silently skipped. |

There is no delete node anywhere in this workflow, and n8n's Execute Command / SSH nodes
are blocked at the instance level via `N8N_DISABLE_NODES`.

### 7.2 Independent chain verification

`Code: Accumulate And Verify Chain` re-links `prev_hash → hash` across every exported
entry **itself**, rather than trusting a backend `chain_ok` boolean. The whole value of a
hash chain is that a reader can check it without trusting the writer.

On any discontinuity the workflow:

1. collects every break (not just the first),
2. escalates to `INTERNAL_ESCALATION_WEBHOOK` as `critical`,
3. `Stop and Error` with a message containing `AUDIT_CHAIN_BREAK`, which WB-00 recognises
   as critical and escalates again,
4. **writes nothing and does not advance the cursor.**

It never "repairs" a chain. A broken chain is evidence, and evidence is not something an
automation layer gets to tidy up.

**Honest limit, stated in every manifest:** this verifies *link continuity* only. It does
not recompute each entry's digest — that needs the backend's exact hashing rule and is
FUTURE work. And an append-only file on a normal volume is not WORM storage. Real
immutability needs a write-once volume or an external notarisation service; n8n cannot
provide it and this design does not pretend otherwise.

### 7.3 Node-by-node

| # | Node | Input | Output |
|---|---|---|---|
| 1 | Daily 02:30 IST | — | tick |
| 2 | Code: Load Cursor | static data | `{cursor, prev_hash, page_size, max_pages}` |
| 3 | HTTP GET: Audit Page | cursor | `{statusCode, body}`; error → node 11 |
| 4 | Code: Accumulate And Verify Chain | page | `{collected[], chain_breaks[], has_more, cursor}` |
| 5 | If: More Pages | — | true → node 3 (loop); false → node 6 |
| 6 | If: Chain Broken | `chain_breaks.length > 0` | true → escalate + Stop; false → node 7 |
| 7 | Code: Build Export | entries | NDJSON blob + manifest |
| 8 | If: Anything To Archive | — | true → node 9; false → Nothing New |
| 9 | Append Audit Archive | NDJSON | appended to `audit-YYYY-MM.jsonl`; error → Stop |
| 10 | Write Run Manifest | manifest | `manifests/manifest-<stamp>-<run_id>.json` |
| 11 | Code: Commit Cursor | — | advances static data **only now** |
| 12 | Notify Export Result | — | ops channel |

A `max_pages` cap (default 200 × 500 = 100 000 entries) bounds the run; hitting it sets
`hit_page_cap: true`, raises the notification to `warning`, and leaves the cursor
mid-range so the next run continues cleanly.

### 7.4 Example request, response, manifest

```http
GET /audit/log?cursor=&limit=500&order=asc
```

```json
{
  "items": [
    { "id": 8841, "actor": "safety_incident_agent", "action": "draft_created",
      "prev_hash": "a91f…", "hash": "c03d…", "timestamp": "2026-09-15T18:02:11Z" },
    { "id": 8842, "actor": "shift_engineer_02", "action": "approval_rejected",
      "prev_hash": "c03d…", "hash": "7e5b…", "timestamp": "2026-09-15T18:09:47Z" }
  ],
  "next_cursor": "8842"
}
```

```json
{
  "manifest_version": "1.0",
  "export_run_id": "1187-1758000600000",
  "exported_at": "2026-09-16T02:30:12Z",
  "exported_by": "n8n:WB-04",
  "entry_count": 2,
  "range": {
    "first_entry_id": 8841, "first_prev_hash": "a91f…",
    "last_entry_id": 8842, "last_hash": "7e5b…"
  },
  "chain_verification": {
    "method": "local_prev_hash_relink",
    "continuous": true,
    "breaks": [],
    "note": "Link continuity only. This does NOT recompute entry digests… Nor is this WORM storage…"
  },
  "immutability": { "write_mode": "append_only", "overwrites_performed": 0, "prior_records_modified": 0 }
}
```

### 7.5 Error handling and retry

| Failure | Route | Retry | Cursor |
|---|---|---|---|
| `/audit/log` 404/501 | exit as `unavailable`, nothing written | none | unchanged |
| `5xx` / unreachable | `Stop and Error` → WB-00 | node: 3 tries, 15 s | unchanged |
| **Chain break** | escalate `critical` → `Stop and Error` | **none** | **unchanged** |
| Archive write fails | `Stop and Error` | none | **unchanged — range retried** |
| Manifest write fails | `Stop and Error` | none | unchanged |
| Notification fails | `continueRegularOutput` | 3 tries | already committed |

The invariant: **every failure path leaves the cursor untouched.** Re-export is safe
(the archive is append-only and manifests are unique); a skipped range would not be.

---

## 8. WB-00 — Shared error handler

**File:** `00-wb-error-handler.json`

Every other workflow names this one in `settings.errorWorkflow`. It:

1. normalises both Error Trigger shapes (post-trigger failure and trigger-activation
   failure);
2. **redacts** `Bearer …`, `token=`, `api_key=`, `password=`, `secret=` from the message
   before it leaves the box — stack traces routinely echo request bodies;
3. appends the **full** record to `workflow-errors-YYYY-MM-DD.jsonl` on the local volume;
4. sends the **safe** summary to the ops channel;
5. escalates to the duty engineer only when the message matches
   `AUDIT_CHAIN_BREAK|TAMPER`.

Every notification carries the line *"No plant action is implied. This is a
workflow-automation failure only."* — so a 3 a.m. alert is never mistaken for a process
alarm.

---

## 9. Retry policy at a glance

| Node class | `retryOnFail` | `maxTries` | `waitBetweenTries` | `onError` | Reasoning |
|---|---|---|---|---|---|
| Ingest (text) | ✔ | 3 | 20 s | `continueErrorOutput` | slow, CPU-bound, worth retrying |
| P&ID OCR process | ✔ | 2 | 30 s | `continueErrorOutput` | minutes-long on CPU; retrying twice is already expensive |
| Approval queue `GET` | ✔ | 3 | 10 s | `continueErrorOutput` | cheap, read-only |
| Notification send | ✔ | 4 | 15 s | `continueErrorOutput` | highest-value delivery in the system |
| Escalation send | ✔ | 5 | 10 s | `continueRegularOutput` | last resort must try hardest |
| Audit page `GET` | ✔ | 3 | 15 s | `continueErrorOutput` | idempotent read |
| Status probes | ✔ | 2–3 | 5 s | `continueRegularOutput` | must degrade, never cancel |
| Audit archive write | ✖ | — | — | `continueErrorOutput` → Stop | never retry a partial write blindly |
| FUTURE endpoints | ✖/2 | — | — | `continueRegularOutput` | a missing endpoint must not fail the run |

Two rules behind the table: **never retry a non-idempotent write**, and **never retry a
deterministic rejection** (`4xx`, `409`) — those need a human, and a retry loop only
hides that.

---

## 10. Security considerations

| # | Concern | Control |
|---|---|---|
| 1 | No hosted AI | No OpenAI / Anthropic / Gemini / hosted-embedding / hosted-vector / hosted-OCR node exists in any workflow. n8n's container is on an `internal: true` Docker network — enforced by infrastructure, not by workflow discipline (§7). |
| 2 | n8n as a new attack path to OT | n8n never leaves the advisory subnet. No SCADA/DCS/Modbus/OPC node; no shell (`N8N_DISABLE_NODES` blocks Execute Command and SSH). |
| 3 | Secret leakage | API tokens live in n8n credentials (encrypted with `N8N_ENCRYPTION_KEY`), not in `$env` — `$env` is readable from any expression since `N8N_BLOCK_ENV_ACCESS_IN_NODE` defaults to `false`. WB-00 redacts bearer tokens from error text. |
| 4 | Confidential content on an unprotected channel | WB-02 forwards identifiers and a deep link only; §10 classification tiers are enforced by the workbench UI, not by a chat client. |
| 5 | Prompt injection via ingested documents or API payloads | WB-02's guard treats retrieved content as data (§19) and aborts on embedded action directives. n8n never places document text in a model context — it has no model. |
| 6 | Filesystem traversal / arbitrary read | `N8N_RESTRICT_FILE_ACCESS_TO=/data/raw:/data/n8n`, `N8N_BLOCK_FILE_ACCESS_TO_N8N_FILES=true`, `data/raw` mounted **read-only**, plus a path-prefix and filename allowlist in WB-01. |
| 7 | Corpus tampering | n8n cannot write to `data/raw` at all. Backend SHA-256 dedup means a swapped file becomes a new revision, not a silent overwrite. |
| 8 | Audit rewriting | append-only writes, unique manifests, no delete node, cursor-after-commit, abort on chain break. |
| 9 | Auto-approval by accident or by edit | GET-only queue call + runtime method assertion + no decision field anywhere in the JSON. Receipt endpoint is a sub-resource, disabled by default. |
| 10 | Webhook spoofing (future push path) | Webhook node uses Header Auth and stays disabled until the backend can sign its calls. |
| 11 | Execution data retention | `EXECUTIONS_DATA_PRUNE=true`, `EXECUTIONS_DATA_MAX_AGE=336` (14 days) — execution payloads may contain document filenames and approval IDs. |
| 12 | Telemetry egress | `N8N_DIAGNOSTICS_ENABLED=false`, version notifications, templates and personalisation all off. Belt and braces, given the network is already internal. |
| 13 | Editor access | n8n owner account + SSO where available; the editor is loopback-bound and reached through the internal reverse proxy. Anyone who can edit a workflow can change what it calls — treat editor access as privileged, consistent with the insider-threat scope §19 already names as out of scope. |

---

## 11. Importing and commissioning

1. Create the two Header Auth credentials named exactly as in §3.1.
2. Import `00-wb-error-handler.json` **first**; note its workflow ID.
3. In each of `01`–`04`, replace `REPLACE_WITH_WB00_WORKFLOW_ID` in
   `settings.errorWorkflow` with that ID (or set it in the UI under
   *Workflow → Settings → Error Workflow*).
4. Import `01`–`04`. n8n rebinds credentials by name; `REPLACE_WITH_CREDENTIAL_ID` is
   replaced automatically once the named credential exists.
5. Set the environment variables from §3.2 and restart n8n.
6. **Commission in this order, with the schedule still inactive**, using *Execute
   Workflow* manually each time:
   - WB-03 first — it is read-only and tells you which endpoints actually answer;
   - WB-01 next, with one small synthetic PDF in `data/raw/sops/source/`;
   - run WB-01 a second time and confirm the outcome is `duplicate`, not a re-ingest;
   - WB-02 with `WB_APPROVAL_RECEIPTS_ENABLED=false`;
   - WB-04 last, and diff the archive file before and after to confirm append-only
     behaviour.
7. Only then activate the schedules.
8. Diff every payload against `GET /openapi.json` and correct the field lookups in the
   Code nodes where your actual schema differs from the illustrative shapes here.

`typeVersion` values target current n8n. On import into a newer instance n8n may migrate
nodes forward; re-export after import if you want the JSON in the repository to match
what is running.

---

## 12. What this design deliberately does not do

- **No model fine-tuning, no training, no evaluation runs.** The 75-case model-evaluation
  benchmark is a reference asset; nothing here reads, modifies or feeds it to a model.
- **No answer generation, no routing, no agents.** That is LangGraph's job and stays there.
- **No retrieval calls.** `POST /knowledge/retrieve` exists, but retrieval belongs inside
  the agent graph where the Guardrail can see it.
- **No WORM guarantee.** §7.2 says why, and what would actually be needed.
- **No authorisation.** `access_scope` is metadata, not authentication (Phase 3B2), and
  n8n does not change that. When RBAC lands, these workflows should get a service
  identity with read-only scopes — the token header is already in place for it.

---

### Sources

- Uploaded project documents: `Sovereign_Agentic_Workbench_SIH26117_Master_Report.pdf`
  (§7, §10, §11, §16, §17, §19, §20, §21), `phase3a.md`, `phase3b1.md`, `phase3b2.md`,
  `README.md`, `model-evaluation-spec.md`.
- [n8n — Read/Write Files from Disk](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.readwritefile/)
- [n8n — Local File Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.localfiletrigger/)
- [n8n — Error Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.errortrigger/)
- [n8n — Handle errors gracefully](https://docs.n8n.io/build/flow-logic/handle-errors-gracefully/)
- [n8n — Security environment variables](https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/security/)
- [n8n — HTTP Request node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/)
