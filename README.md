# Sovereign On-Premise Agentic AI Workbench

SIH 2026 project. Phases 0–2 provide a FastAPI backend, a React/Vite dashboard,
and a PostgreSQL/SQLAlchemy foundation with Alembic migrations and placeholder APIs.

## Fixed architecture

React frontend → FastAPI backend → LangGraph Orchestrator → Domain Agents →
Guardrail Agent → Human Approval

Planned supporting components: PostgreSQL for structured data, Qdrant for vector
storage, Ollama for local development, vLLM as a future deployment option, and
Docker Compose. Only local/open-weight models will be used; hosted model APIs
are excluded.

## Current scope — Phase 2

The frontend dashboard preserves its backend health connection. PostgreSQL runs
through `infra/docker-compose.yml`; nine database models and an initial Alembic
migration prepare structured storage. Foundation API routes return placeholders.
Agents, LangGraph, authentication, Qdrant, RAG, model inference, approval workflow,
and audit hash chaining are not implemented.

See [backend setup instructions](backend/README.md) for Windows commands.
Copy `.env.example` to a local root `.env` if configuration is needed; never
commit real secrets or local model weights.

Health endpoint: `GET http://127.0.0.1:8000/health`

```json
{"status":"ok","service":"sovereign-agentic-workbench-backend"}
```
