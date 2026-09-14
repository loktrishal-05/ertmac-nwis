# Sovereign On-Premise Agentic AI Workbench

SIH 2026 project. Phase 0 provides a minimal FastAPI backend with environment
configuration, localhost CORS, and a health endpoint.

## Fixed architecture

React frontend → FastAPI backend → LangGraph Orchestrator → Domain Agents →
Guardrail Agent → Human Approval

Planned supporting components: PostgreSQL for structured data, Qdrant for vector
storage, Ollama for local development, vLLM as a future deployment option, and
Docker Compose. Only local/open-weight models will be used; hosted model APIs
are excluded.

## Phase 0 scope

Only the backend scaffold is implemented. Frontend, model, data, infrastructure,
and documentation directories are placeholders. Agents, LangGraph, databases,
authentication, Qdrant, model inference, and deployment configuration are not yet
implemented.

See [backend setup instructions](backend/README.md) for Windows commands.
Copy `.env.example` to a local root `.env` if configuration is needed; never
commit real secrets or local model weights.

Health endpoint: `GET http://127.0.0.1:8000/health`

```json
{"status":"ok","service":"sovereign-agentic-workbench-backend"}
```
