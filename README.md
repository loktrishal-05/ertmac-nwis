# Sovereign On-Premise Agentic AI Workbench

SIH 2026 project. Phases 0–3B2 provide FastAPI, a React/Vite dashboard,
PostgreSQL/SQLAlchemy, and local PDF evidence retrieval with Docling, BGE, and Qdrant.
See [Phase 3A guide](docs/phase3a.md) for ingestion and retrieval setup.
See [Phase 3B1 guide](docs/phase3b1.md) for local P&ID/image OCR preparation.
See [Phase 3B2 guide](docs/phase3b2.md) for hybrid retrieval, the explicit Qdrant
migration, local reranking, OCR text indexing, and retrieval evaluation.

## Fixed architecture

React frontend → FastAPI backend → LangGraph Orchestrator → Domain Agents →
Guardrail Agent → Human Approval

Planned supporting components: PostgreSQL for structured data, Qdrant for vector
storage, Ollama for local development, vLLM as a future deployment option, and
Docker Compose. Only local/open-weight models will be used; hosted model APIs
are excluded.

## Current scope — Phase 3B2

The frontend dashboard preserves its backend health connection. PostgreSQL and
Qdrant run through `infra/docker-compose.yml`. Alembic adds document revision state
without replacing existing tables. PDFs are extracted, chunked, embedded locally,
and retrieved with source citations. Final runtime uses local embeddings. No
hosted inference API is required. Agents, LangGraph, authentication, answer
generation, approval workflow, and audit hash chaining are absent. P&ID OCR now
produces text/coordinate/region artifacts using local PP-OCRv5. OCR does not
establish process topology or pipe connectivity.
Retrieval combines dense BGE and local sparse search with RRF and optional BGE
reranking. A separate indexing endpoint makes OCR text searchable with its original
confidence and coordinate metadata. No answers are generated.

See [backend setup instructions](backend/README.md) for Windows commands.
Copy `.env.example` to a local root `.env` if configuration is needed; never
commit real secrets or local model weights.

Health endpoint: `GET http://127.0.0.1:8000/health`

```json
{"status":"ok","service":"sovereign-agentic-workbench-backend"}
```
