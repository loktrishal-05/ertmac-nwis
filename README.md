# eRTMAC-NWIS backend - SIH26121

The active backend pivot is documented in [docs/nwis/README.md](docs/nwis/README.md).
Its specification is the authorized [SIH26121 master PDF](docs/nwis/reference/eRTMAC_NWIS_Master_Report_SIH26121.pdf).
The older Sovereign/SIH26117 documentation below is historical platform reference, not NWIS product requirements.

# Sovereign On-Premise Agentic AI Workbench

Current local deployment and runtime validation: [Phase 7 PowerShell guide](docs/phase7.md).

SIH 2026 project. Phases 0–5B provide FastAPI, a React/Vite dashboard,
PostgreSQL/SQLAlchemy, local PDF/P&ID evidence retrieval with Docling, BGE, and
Qdrant, structured maintenance/sensor data ingestion and query, and a local
model gateway abstraction over Ollama.
See [Phase 3A guide](docs/phase3a.md) for ingestion and retrieval setup.
See [Phase 3B1 guide](docs/phase3b1.md) for local P&ID/image OCR preparation.
See [Phase 3B2 guide](docs/phase3b2.md) for hybrid retrieval, the explicit Qdrant
migration, local reranking, OCR text indexing, and retrieval evaluation.
See [Phase 3C guide](docs/phase3c.md) for maintenance/sensor CSV ingestion,
deterministic feature extraction, and anomaly observations.
See [Phase 4A guide](docs/phase4a.md) for the local model gateway: structured
output, tool-call parsing, and the Ollama/vLLM runtime abstraction.
See [Phase 4R repair record](docs/phase4-repair.md) for current specialist
agent safety and evidence-handling status.
See [Phase 5A governance boundary](docs/phase5a.md) and its
[validation record](docs/phase5a-validation.md) for immutable pending proposals.
See [Phase 5B approval workflow](docs/phase5b.md) and its
[validation record](docs/phase5b-validation.md) for local authentication and
the authenticated approve/reject/revoke/release workflow.

## Fixed architecture

React frontend → FastAPI backend → LangGraph Orchestrator → Domain Agents →
Guardrail Agent → Human Approval

Planned supporting components: PostgreSQL for structured data, Qdrant for vector
storage, Ollama for local development, vLLM as a future deployment option, and
Docker Compose. Only local/open-weight models will be used; hosted model APIs
are excluded.

## Current scope — Phase 5B

The frontend dashboard preserves its backend health connection. PostgreSQL and
Qdrant run through `infra/docker-compose.yml`. PDFs and P&IDs are extracted,
chunked/OCR'd, embedded locally, and retrieved with source citations; maintenance
and sensor CSVs are ingested and queryable with deterministic feature extraction
and factual anomaly observations. Final runtime uses local embeddings and local
model inference (Ollama, development). No hosted inference API is required or
permitted. Phase 4R includes the local model gateway and LangGraph specialist
routes for advisory knowledge, safety, maintenance, and optimization outputs.
Phase 5A added immutable governed revisions and server-owned pending review
after specialist validation. Phase 5B adds local Argon2id-backed
username/password authentication and a real authenticated reviewer who can
approve/reject/revoke the exact immutable revision they inspected, with a
fail-closed advisory release gate; approval never grants plant-control
capability. Phase 4 is accepted with conditions; Phase 5A and 5B are complete
with live PostgreSQL validation. Phase 5C (tamper-evident audit chain) has not
started.
Audit hash chaining, cryptographic evidence integrity, pre-routing guardrails,
and plant-control capabilities remain absent. OCR does not establish process
topology or pipe connectivity, and sensor anomaly observations are factual,
never diagnoses.

See [backend setup instructions](backend/README.md) for Windows commands.
Copy `.env.example` to a local root `.env` if configuration is needed; never
commit real secrets or local model weights.

Health endpoint: `GET http://127.0.0.1:8000/health`

```json
{"status":"ok","service":"sovereign-agentic-workbench-backend"}
```
