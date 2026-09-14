# Phase 3A — Local document evidence retrieval

The existing React → FastAPI → future LangGraph → domain agents → guardrail →
human approval architecture remains unchanged. This phase adds a backend evidence
service only:

PDF in `data/raw` → PyMuPDF inspection → Docling extraction → structured JSON and
Markdown → section-aware chunks → regex tags → local BGE embeddings → Qdrant →
retrieved chunks with stored citations.

Final runtime uses local embeddings. No hosted inference API is required.
There is no answer generation, agent execution, RAG answering, OCR execution,
sensor feature extraction, or P&ID topology reasoning. Hugging Face is used only
by the explicit model-artifact download command.

## Windows setup

From the repository root, with Docker Desktop running:

```powershell
docker compose -f infra/docker-compose.yml config --quiet
docker compose -f infra/docker-compose.yml up -d --wait
docker compose -f infra/docker-compose.yml exec postgres pg_isready -U postgres -d sovereign_workbench
Invoke-RestMethod http://127.0.0.1:6333/healthz
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m scripts.download_models --docling
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The downloader fetches BAAI/bge-base-en-v1.5 into `models/bge-base-en-v1.5` and,
with `--docling`, layout/table artifacts into `models/docling`. It excludes OCR,
picture description, and VLM models. Downloads can be significant. Missing BGE
artifacts cause a clear dependency failure; they are never replaced by a different
model. In air-gapped deployment copy the prepared `models/` directory onto the
host. Sentence Transformers loads only local files, with remote code disabled.
CPU execution is supported; Sentence Transformers automatically selects CUDA when
available. The model is lazily initialized and reused within each backend process.

Docling is primary, with OCR and remote services disabled. If Docling artifacts
are missing or conversion is incomplete, native-text PyMuPDF fallback is explicit
in the response warnings and extraction report. Fallback can lose table structure.
Low-text image pages in otherwise native PDFs prevent indexing of the entire file
and return `ocr_required`; no page contents are fabricated. Blank/image scan
detection is heuristic, so inspect reports before using new document families.

## Configuration

Root `.env` values use these exact names (process environment takes precedence):

```dotenv
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=knowledge_chunks_v1
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
EMBEDDING_DIMENSION=768
CHUNK_TARGET_TOKENS=400
CHUNK_MAX_TOKENS=500
CHUNK_OVERLAP_TOKENS=60
```

The existing DATABASE_URL/root `.env` handling and five-second database connection
timeout are preserved. `VITE_API_BASE_URL` stays in the frontend environment file.
Qdrant uses official image `qdrant/qdrant:v1.17.0`, a persistent named volume, and
localhost ports 6333/6334; PostgreSQL retains its existing service and volume.

Collection initialization is idempotent and validates compatibility instead of
recreating incompatible collections. The named `dense` vector has size 768 and
cosine distance. Payload indexes: document_type, document_id, document_version_id,
facility_id, unit_id, equipment_tags, instrument_tags, synthetic, access_scope,
language. Sparse vectors/BM25 are reserved for Phase 3B, not implemented.

## Ingest a PDF

Place a PDF under `data/raw/sops/source/` (or another raw subdirectory). From a
PowerShell terminal:

```powershell
$ingestBody = @{
  source_path = 'sops/source/example.pdf'
  title = 'Reactor Startup SOP'
  document_type = 'sop'
  revision = '1'
  facility_id = 'prototype'
  unit_id = 'unit-1'
  synthetic = $false
  access_scope = 'internal'
} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/documents/ingest -Method Post -ContentType 'application/json' -Body $ingestBody
```

This is a local prototype input API, not file upload or arbitrary URL ingestion.
Paths are restricted to `data/raw`, PDFs to 20 MiB and 100 pages, and language to
English for the approved embedding model. Optional metadata includes document_date,
effective_date and document_id. Supply an existing document_id to attach a new
source revision; otherwise a new logical Document is created.

Exact SHA-256 revisions are unique across ingestion. Repeated source bytes and
metadata return the original IDs with `duplicate` and no re-embedding. Conflicting
metadata returns 409; concurrent processing of identical bytes also returns 409.
PostgreSQL advisory transaction locks protect deduplication. Changed bytes are a
new revision. Failed embedding/indexing work is marked failed and can be retried
with the same metadata. Old successful revisions remain searchable; use a version
filter when a specific revision is required.

Qdrant and PostgreSQL do not share a distributed transaction. Retries replace only
their own version points, and retrieval restricts results to PostgreSQL's indexed
versions, excluding partial/orphan writes. A crash can leave ignored artifacts or
unreferenced vectors; cleanup tooling is deferred. Do not delete Qdrant storage
independently of PostgreSQL: duplicate detection assumes successful indexed
versions remain present. The synchronous prototype request may take time on CPU;
background jobs, upload streaming, and production concurrency limits are deferred.

## Chunk and citation contracts

The actual BGE tokenizer counts the complete embedding input, including document
title, section hierarchy, equipment context, and special tokens. Target 400,
hard maximum 500, overlap up to 60 tokens. The 512-token model limit is checked
again before encoding; silent truncation is rejected. Complete small blocks,
numbered steps, and tables are retained when they fit. Large blocks split near
newline/word boundaries using original character offsets, with within-section
overlap. Isolated sections below roughly 80 tokens are preserved rather than
merged with unrelated sections or discarded. Long/ambiguous headings may require
human correction of extraction; parser structure is not treated as ground truth.

Every payload validates all required identity, source hash/URI, title/revision/date,
facility/unit/tag, section/content/token, page/bounding-box, extraction/OCR,
language/synthetic/access-scope, and pipeline/timestamp fields. Missing source
dates/revisions are null; missing section information is an empty list, never an
invented heading. Hashes identify original bytes. Source URIs are data-relative
paths, not public download URLs. Regex patterns are configurable through the
`extract_tags` function and cover common equipment/instrument identifiers and
conservative quoted-diameter line-number forms.

## Retrieve evidence

```powershell
$retrievalBody = @{
  query = 'What procedure applies to pump P-101A?'
  top_k = 6
  filters = @{ synthetic = $true }
} | ConvertTo-Json -Depth 4
Invoke-RestMethod http://127.0.0.1:8000/knowledge/retrieve -Method Post -ContentType 'application/json' -Body $retrievalBody
```

BGE's retrieval instruction is applied to queries only. Embeddings are normalized
and batchable. Exact detected equipment/instrument tags constrain retrieval unless
explicit tag filters are supplied; unmatched tags can therefore yield no results.
Optional filters correspond to the indexed metadata fields. Results contain IDs,
dense similarity scores, evidence content, and citations copied from the retrieved
payload: title, filename, source URI/hash, revision, section path, page range,
bounding boxes, and quote. Quotes equal stored chunk content. No citation names,
page numbers, IDs, or answers are generated by a language model.

`access_scope` is metadata/filtering only, not authorization. Authentication/RBAC
is still absent. `/sovereignty/proof` remains the Phase 2 static declaration, not
network attestation or a measured outbound-call counter. The frontend and other
Phase 0–2 API contracts remain unchanged.

## Validation

```powershell
# backend/
.\.venv\Scripts\python.exe -m compileall -q app alembic scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m scripts.smoke_knowledge
```

The opt-in smoke test creates one immutable synthetic/native PDF, runs the real
FastAPI ingestion/retrieval handlers against PostgreSQL/Qdrant and local BGE,
checks duplicate idempotency, verifies dimensions/norms and citations, and writes
an ignored report to `data/indexes/ingestion_manifests/phase3a_smoke_result.json`.
It leaves the synthetic document and indexed points for inspection. Unit tests
use an in-memory Qdrant client and a deterministic tokenizer; the smoke test uses
the actual BGE tokenizer/model. Run frontend `npm run build`, `npm run lint`, and
root `git diff --check` as regression checks.

Phase 3B work remains: OCR, sparse/BM25 or hybrid retrieval, broader extraction
evaluation, and any separately approved richer P&ID/multimodal processing. This
phase adds no answer-generation runtime or agents.
