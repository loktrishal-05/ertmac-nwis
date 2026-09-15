# Phase 3B1 validation report

Revalidated on 2026-09-15 against the existing uncommitted implementation, then
completed uncertainty status, immutable image retry handling, API coverage, and
fresh live smoke checks. All results below describe this validation run.

## Architecture and scope

No root architecture redesign. Added a local P&ID OCR branch beneath the existing
FastAPI document API, using existing Document/DocumentVersion PostgreSQL records.
No frontend behavior, Qdrant configuration, collection, schema, or migration changed.
OCR text is artifact-only and is not indexed. No agents, answer generation, image
embeddings, VLM, sparse/BM25, reranking, sensor processing, or topology inference
was implemented.

## Implementation

- New POST /documents/pid/process accepts a JSON path restricted to
  data/raw/pids/source plus title/revision/synthetic/preprocessing metadata.
- PDF pages render with PyMuPDF at 300 DPI by default (300 to 400 configurable).
  PNG/JPG/JPEG metadata and EXIF orientation are preserved. Raw bytes are immutable.
- OpenCV preprocessing creates separate images: grayscale, CLAHE contrast,
  optional adaptive threshold/median denoising, and explicit quarter-turn rotation.
- Local PP-OCRv5 predictor initializes lazily and is reused behind a lock.
  Page-wise processing bounds memory. CPU was tested; GPU selection is implemented
  for a compatible CUDA PaddlePaddle installation, but GPU was not tested here.
- Raw text, normalized text, confidence, bbox, polygon, page, rendered-image URI,
  dimensions, engine, category, identified tags and `ocr_derived=true` form each
  normalized detection. Status is `unverified`, or `ambiguous` below confidence
  0.60; even high-confidence regex matches are never marked verified.
  Inverse transforms map processed-image coordinates onto the stored rendered page.
- Regex classification covers equipment, instruments, valves, line numbers,
  temperature/pressure values, drawing titles, revision and other text. O/0 and
  I/1 are never guessed. Existing Phase 3A identifier patterns are reused.
- Regions are bounded nearby text groups with stable UUIDs, text items, combined
  text, tags, bbox, page, source URI and conservative labels. They are not connections.
- Artifacts include rendered/preprocessed images, OCR JSON, region JSON and a
  source/document/version-linked manifest under data/processed/pids.
- Existing checksum uniqueness/advisory locks prevent duplicate processing.
  pid_processing/pid_processed/pid_failed use existing string status fields and
  JSONB metadata. No relational table changes were necessary. Identical successful
  requests return the same IDs without rerunning OCR; conflicts return 409.
- Retry processing compares existing rendered/preprocessed image pixels and reuses
  matching files without writing them. Differing images fail with originals preserved.

## Dependencies

Added direct requirements:

- paddleocr>=3.3,<3.4: installed 3.3.3
- paddlepaddle>=3.2,<3.3: installed CPU version 3.2.2
- opencv-python==4.10.0.84: matches PaddleX's OpenCV-contrib pin
- pillow>=10,<13: installed 12.3.0; now explicit for image metadata/validation

PaddleX 3.3.13 and opencv-contrib-python 4.10.0.84 are transitive dependencies.
Model artifacts: PaddlePaddle/PP-OCRv5_server_det and PP-OCRv5_server_rec, stored
under models/paddleocr. Both were already present; no package or model downloads
were needed for this run. Runtime uses explicit local model paths, with the host-connectivity probe
disabled. No hosted OCR/AI API was used.

## Validation results

| Validation | Result |
| --- | --- |
| Python compilation | Passed |
| Backend tests | 37 passed (19 existing + 18 P&ID tests); no skips |
| Alembic check | No new upgrade operations detected |
| pip check | No broken requirements |
| Docker Compose config | Passed |
| PostgreSQL | Existing container healthy; accepting connections |
| Qdrant healthz | healthz check passed |
| Frontend build | Passed after approved subprocess retry |
| Frontend lint | Passed |
| git diff --check | Passed; line-ending warnings only |
| Fresh real PaddleOCR smoke | Passed on local CPU; 46.8 seconds including initialization |
| Fresh Phase 3A smoke | Passed: Docling extraction, BGE embedding, Qdrant indexing/retrieval and citations |
| Evaluation assets | Specification, cases and config SHA-256 unchanged; evaluation manifest hashes match |

Live fixture:
`data/raw/pids/source/phase3b1_synthetic_7a9f72585f0444359f58b9ab5b960ebb.png`,
1200 by 850 pixels, generated independently of the evaluation pack.
One page produced 8 detections and 6 spatial regions. All six requested identifiers
were recognized: P-101A, V-101, E-101, TT-101, PT-101, FV-101. Their recognition
confidence ranged from approximately 0.924 to 0.999. Every detection has real
polygons/bounding boxes. The drawing title and revision were also recognized.

The smoke test verified artifact files, duplicate version IDs, a 409 metadata
conflict, unchanged original SHA-256, and unchanged Qdrant point count (2 existing
Phase 3A points). No P&ID vectors were added. PDF rendering and JPEG/EXIF behavior
were tested separately in unit tests; live OCR used the PNG fixture.

Document ID: `beadb764-f9de-4c7e-8eb8-4ee638f4cab0`.
Version ID: `06fbb9a2-fdb4-4d41-8511-5eac80797439`.
Source SHA-256:
`7bb140af246b05efabfd6bf3744ed2dc168ffc8360c66aea12c7711f22986df7`.
P-101A's real bbox is `[95, 127, 357, 191]`, confidence `0.9983885288238525`,
page 1, status `unverified`. Its original four-point polygon is in the OCR JSON.

The subsequent fresh Phase 3A regression created version
`db0b7728-722e-4ea2-bdec-c7ec657565a7` with one Docling chunk and no warnings.
Real BGE vectors were 768-dimensional with unit norm. Retrieval returned page-one
source/hash/quote/bbox metadata at score `0.7561222`; the quote matched stored
content. The new synthetic SOP raised Qdrant's count from 2 to 3. Duplicate
ingestion added no points, conflicting metadata returned 409, and source bytes
were unchanged. Its report is `data/indexes/ingestion_manifests/phase3a_smoke_result.json`.

Additional tests cover API response validation through the actual route and
processing service, source hashes and modification times, failed-OCR retries,
image preservation, low-confidence candidate status, escaping symlinks, and new
source revisions preserving prior document evidence.
Unit tests replace database persistence and OCR inference; live smoke tests use
real PostgreSQL, PaddleOCR, Docling, BGE and Qdrant.

Detailed local result (Git-ignored):
`data/processed/pids/manifests/phase3b1_smoke_result.json`.

## Commands used

```powershell
# Repository root
docker compose -f infra/docker-compose.yml up -d --wait
docker compose -f infra/docker-compose.yml config --quiet
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml exec postgres pg_isready -U postgres -d sovereign_workbench
Invoke-RestMethod http://127.0.0.1:6333/healthz
git diff --check

# backend/
.\.venv\Scripts\python.exe -m scripts.smoke_pid --fresh
.\.venv\Scripts\python.exe -m scripts.smoke_knowledge --fresh
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q app alembic scripts tests
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pip check

# frontend/
npm run build
npm run lint
```

## Errors resolved and remaining warnings

- Sandbox restrictions blocked Docker pipe access and Vite's esbuild subprocess.
  Approved retries completed successfully. OCR ran using existing local models.
- Preserved the existing Windows PyTorch-before-Paddle DLL workaround, oneDNN CPU
  acceleration, and PNG verification through a fresh decoder.
- Fixed rendered/preprocessed image overwriting on retry and added explicit OCR
  uncertainty status. No alternate OCR engine or model inference API was used.
- Fresh smoke modes require actual processing, so previous duplicate records cannot
  masquerade as fresh OCR or extraction validation.
- Nonfatal upstream warnings remain: no ccache, native oneDNN logging initialization,
  Starlette's httpx TestClient deprecation, and Git LF-to-CRLF conversion notices.
  None required changing application behavior or installing an unrelated runtime.

## Limitations and remaining work

**OCR-derived labels are evidence, not process topology.** OCR does not establish
pipe connectivity, flow direction,
valve-to-pump connectivity, or process causality. Small/rotated/noisy labels and
ambiguous characters need human review. This is synchronous prototype processing;
large server-model inference can be slow, and no production job queue is added.
Input/pixel/page/detection limits bound practical workloads. Partial processed
artifacts may remain after failed requests; raw sources remain unchanged.
Access scope is metadata only; no authentication/RBAC was added.
Input boundaries assume the local source/artifact directories are controlled by
the application operator; concurrent hostile filesystem replacement is not an
OS-level security boundary. Model confidence is uncalibrated for industrial drawings.

The evaluation specification, 75 cases, configuration and manifest remain unchanged.
No training, benchmark execution, Qwen, Ollama backend integration, LangGraph,
model gateway, or Phase 3C work was performed.

Phase 3B2 was not started and its exact scope has not been specified. Deferred
capabilities remain OCR-text indexing/review extensions if approved, sparse/BM25
retrieval and reranking, and separately scoped multimodal, topology, orchestration,
answer-generation and sensor work. This report does not assign those later
capabilities to an unapproved phase.

## Files created

- `backend/app/api/routes/pid.py`
- `backend/app/schemas/pid.py`
- `backend/app/services/paddle_ocr.py`
- `backend/app/services/pid_identifiers.py`
- `backend/app/services/pid_images.py`
- `backend/app/services/pid_processing.py`
- `backend/app/services/pid_regions.py`
- `backend/scripts/download_pid_models.py`
- `backend/scripts/smoke_pid.py`
- `backend/tests/test_pid.py`
- `docs/phase3b1-validation.md`
- `docs/phase3b1.md`

## Files modified

- `.env.example`
- `README.md`
- `backend/README.md`
- `backend/app/api/router.py`
- `backend/app/core/config.py`
- `backend/requirements.txt`
- `backend/scripts/smoke_knowledge.py` (optional fresh validation mode only)
- `data/README.md`
