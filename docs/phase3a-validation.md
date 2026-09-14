# Phase 3A validation report

Phase 3A is implemented and tested. No Phase 3B work was performed. The existing
frontend and Phase 0?2 non-ingestion API contracts remain intact.

## Implementation

- Qdrant official image v1.17.0, persistent volume, localhost REST 6333/gRPC 6334;
  the existing PostgreSQL service and volume are preserved.
- Collection knowledge_chunks_v1: named dense vector, 768 dimensions, cosine.
  Ten payload indexes cover document/type/version, facility/unit, equipment and
  instrument tags, synthetic, access_scope, and language. Initialization is idempotent.
- Sentence Transformers with BAAI/bge-base-en-v1.5, local-only loading, lazy reuse,
  batches, normalized vectors, automatic device selection, no hosted inference.
- PyMuPDF inspects native text and coordinates. Docling is the primary parser;
  explicit PyMuPDF fallback and ocr_required status prevent invented extraction.
  Markdown, structured JSON, extraction reports, SHA-256, and chunk manifests are saved.
- Chunking uses the BGE tokenizer with contextual headings/equipment: target 400,
  maximum 500, overlap up to 60. Sections remain separate, original text offsets
  preserve quotes, numbered markers and small tables remain intact where possible.
  Short isolated sections are retained instead of mixed with unrelated content.
- Pydantic chunk metadata validates every requested identity, provenance, date,
  section/page/box, classification/tag, extraction/OCR and pipeline field. Unknown
  dates/revisions/OCR values remain null; unknown sections remain empty.
- POST /documents/ingest now accepts a JSON raw-relative PDF path and metadata.
  POST /knowledge/retrieve returns evidence and stored citations without answers.
- Alembic 0002_document_versions adds the source-version/checksum ingestion state.
  PostgreSQL locks/unique checks prevent duplicate ingestion. Retrieval only sees
  indexed revisions, excluding partial Qdrant writes.

## Dependencies added

- qdrant-client>=1.17,<1.18 (installed 1.17.1)
- sentence-transformers>=5.1,<6.0 (installed 5.7.0)
- docling>=2.60,<3.0 (installed 2.127.0)
- pymupdf>=1.26,<2.0 (installed 1.28.2)

The BGE tokenizer is supplied by Sentence Transformers. PyTorch/Transformers and
parser dependencies are transitive requirements, not answer-generation integrations.

## Validation results

| Check | Result |
| --- | --- |
| Python compileall | Passed |
| Backend tests | 19 passed, including Phase 0?2 regression routes |
| pip check | No broken requirements |
| Alembic upgrade head | Applied successfully to live PostgreSQL |
| Alembic current | 0002_document_versions (head) |
| Alembic check | No new upgrade operations detected |
| Docker Compose config | Passed |
| PostgreSQL health | Healthy; pg_isready accepts connections |
| Qdrant healthz | healthz check passed |
| Collection configuration and payload indexes | Verified on live Qdrant |
| Frontend build | Passed after approved sandbox retry |
| Frontend lint | Passed |
| git diff --check | Passed; Git line-ending warnings only |

The live integration script invokes the actual FastAPI handlers with real
PostgreSQL, Qdrant, Docling, and BGE (no mocked embeddings). Unit API regressions
also start a live Uvicorn server. Two tiny synthetic PDFs were created during
validation; raw bytes remained unchanged. The latest source is
phase3a_synthetic_numbered.pdf, revision TEST-1. Docling extracted one chunk with
no fallback warnings; Qdrant has two synthetic points in total. Retrieval returned
real page-one evidence at cosine score approximately 0.7561. The citation quote
matches stored content, including numbered steps. Duplicate ingestion returned
the original version without increasing the point count; metadata conflict returned
409. Real embeddings were verified as 768-dimensional with unit norm.

The machine-local detailed smoke result is Git-ignored at
`data/indexes/ingestion_manifests/phase3a_smoke_result.json`.

## Commands executed

```powershell
# Repository root
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
docker compose -f infra/docker-compose.yml config --quiet
docker compose -f infra/docker-compose.yml up -d --wait
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml exec postgres pg_isready -U postgres -d sovereign_workbench
Invoke-RestMethod http://127.0.0.1:6333/healthz
git diff --check

# backend/
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m scripts.download_models --docling
.\.venv\Scripts\python.exe -m scripts.smoke_knowledge
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q app alembic scripts tests
.\.venv\Scripts\python.exe -m pip check

# frontend/
npm run build
npm run lint
```

## Warnings and limitations

Initial dependency/model downloads, Docker pipe access, and frontend esbuild
execution were blocked by sandbox restrictions. Approved retries succeeded.
All approved embedding and Docling layout/table artifacts downloaded successfully;
no substitute model or hosted inference API was used.

The smoke harness emits a Starlette deprecation warning for its httpx-based
TestClient. Tests still pass; no extra dependency was added only to suppress it.
Git warns about LF-to-CRLF conversion on Windows. The Sentence Transformers
renamed-dimension-method warning was fixed.

This is a synchronous local prototype. Access scope is metadata, not RBAC.
Scan detection is heuristic; PyMuPDF fallback may reduce table structure. Partial
artifacts can remain after failure, but unindexed revisions are not retrieved.
Short isolated sections remain below the usual minimum to preserve evidence.

## Remaining Phase 3B work

OCR, sparse/BM25 or hybrid retrieval, broader extraction/retrieval evaluation,
and separately approved P&ID or multimodal extensions remain unimplemented.
No agents, LangGraph, answer generation, sensor feature extraction, or topology
reasoning was added.

## Files created

- `backend/alembic/versions/0002_document_versions.py`
- `backend/app/api/routes/knowledge.py`
- `backend/app/db/models/document_version.py`
- `backend/app/schemas/knowledge.py`
- `backend/app/services/chunking.py`
- `backend/app/services/embeddings.py`
- `backend/app/services/extraction.py`
- `backend/app/services/ingestion.py`
- `backend/app/services/qdrant_service.py`
- `backend/app/services/retrieval.py`
- `backend/app/services/tags.py`
- `backend/scripts/__init__.py`
- `backend/scripts/download_models.py`
- `backend/scripts/smoke_knowledge.py`
- `backend/tests/test_knowledge.py`
- `data/README.md`
- `data/evaluation/expected_citations.jsonl`
- `data/evaluation/extraction_ground_truth/.gitkeep`
- `data/evaluation/retrieval_questions.jsonl`
- `data/indexes/ingestion_manifests/.gitkeep`
- `data/indexes/qdrant_snapshots/.gitkeep`
- `data/manifests/dataset_licenses.md`
- `data/manifests/documents.csv`
- `data/manifests/equipment.csv`
- `data/manifests/tag_dictionary.csv`
- `data/processed/documents/extraction_reports/.gitkeep`
- `data/processed/documents/markdown/.gitkeep`
- `data/processed/documents/page_images/.gitkeep`
- `data/processed/documents/structured_json/.gitkeep`
- `data/processed/maintenance/normalized/.gitkeep`
- `data/processed/pids/manifests/.gitkeep`
- `data/processed/pids/ocr_json/.gitkeep`
- `data/processed/pids/page_images/.gitkeep`
- `data/processed/pids/regions/.gitkeep`
- `data/processed/sensors/features/.gitkeep`
- `data/processed/sensors/normalized/.gitkeep`
- `data/processed/sensors/windows/.gitkeep`
- `data/raw/incidents/metadata/.gitkeep`
- `data/raw/incidents/source/.gitkeep`
- `data/raw/maintenance/equipment_master/.gitkeep`
- `data/raw/maintenance/work_orders/.gitkeep`
- `data/raw/pids/metadata/.gitkeep`
- `data/raw/pids/source/.gitkeep`
- `data/raw/sensors/faults/.gitkeep`
- `data/raw/sensors/normal/.gitkeep`
- `data/raw/sensors/tag_dictionary/.gitkeep`
- `data/raw/sops/metadata/.gitkeep`
- `data/raw/sops/source/.gitkeep`
- `docs/phase3a-validation.md`
- `docs/phase3a.md`

## Files modified

- `.env.example`
- `.gitignore`
- `README.md`
- `backend/README.md`
- `backend/app/api/router.py`
- `backend/app/api/routes/documents.py`
- `backend/app/core/config.py`
- `backend/app/db/models/__init__.py`
- `backend/app/schemas/document.py`
- `backend/requirements.txt`
- `backend/tests/test_foundation.py`
- `infra/docker-compose.yml`
