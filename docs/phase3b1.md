# Phase 3B1 — Local P&ID OCR preparation

This phase adds a separate FastAPI document-processing route to the existing
architecture. It reuses PostgreSQL Document and DocumentVersion records and the
approved data directories. It does not change the frontend, dense retrieval,
Qdrant collection, or the future orchestration architecture.

```text
data/raw/pids/source/{PDF,PNG,JPG,JPEG}
  → immutable byte snapshot + SHA-256
  → PyMuPDF rendering / image metadata inspection
  → separate OpenCV preprocessed image
  → local PaddleOCR PP-OCRv5
  → normalized text, confidence, pixel polygons and boxes
  → deterministic identifiers and spatial text regions
  → JSON artifacts + document/version processing state
```

**OCR-derived labels are evidence, not process topology.** Phase 3B1 does not infer pipe
connectivity, flow direction, valve-to-pump connectivity, or process causality.
Spatial text groups are not component connections. No VLM, image embeddings,
answer generation, agents, sparse retrieval, reranking, or sensor pipeline runs.

## Install and prepare local models

From the repository root, start the unchanged database services:

```powershell
docker compose -f infra/docker-compose.yml up -d --wait
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m scripts.download_pid_models
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

New direct requirements are PaddleOCR 3.3.x, CPU PaddlePaddle 3.2.x, and OpenCV
4.10.0.84; Pillow is now explicit for image validation/EXIF/resolution handling.
OpenCV's version matches PaddleX's OpenCV-contrib pin; these upstream packages
share `cv2`. The full dependency set is checked with `pip check` and regression
tests. Existing PyMuPDF, PostgreSQL, and Qdrant dependencies remain.

The download command fetches only the official PaddlePaddle model repositories
`PP-OCRv5_server_det` and `PP-OCRv5_server_rec` into `models/paddleocr/`. Those
Git-ignored directories contain inference weights/configuration. Hugging Face is
used for artifact download only. Runtime passes explicit local paths and disables
PaddleX's model-host connectivity probe. Missing weights cause a clear dependency
failure; the engine is never replaced with another OCR system.

PaddleOCR initializes lazily and reuses one predictor per process. A lock serializes
predictor access. Pages are processed individually to bound memory; the service
accepts multiple pages. CPU is supported by the installed runtime.
The fresh CPU validation took 46.8 seconds including initialization. Larger pages
can take several minutes; keep the request open and use the smoke trace option for diagnosis.
A compatible
GPU-enabled PaddlePaddle installation is selected automatically when CUDA devices
are available; the CPU package does not itself supply CUDA. Do not install CPU
and GPU PaddlePaddle distributions together. On Windows, the existing PyTorch
runtime is imported before PaddlePaddle to avoid a DLL loading conflict.

Paddle/PaddleX may create local cache directories under the user's home during
first initialization; restricted environments must grant the necessary write
access. Models themselves are loaded from the project model directory. No hosted
OCR or inference API is used.

## Process a drawing

Place a source file under `data/raw/pids/source/`. Never overwrite an existing
source revision. Send a JSON request (there is no arbitrary URL or file upload):

```powershell
$pidBody = @{
  source_path = 'TEP-100-PID-001.pdf'
  title = 'Prototype P&ID'
  revision = 'A'
  synthetic = $false
  render_dpi = 300
  preprocessing = @{
    grayscale = $true
    contrast_normalization = $true
    adaptive_threshold = $false
    denoise = $false
    rotation_degrees = 0
  }
} | ConvertTo-Json -Depth 4
Invoke-RestMethod http://127.0.0.1:8000/documents/pid/process -Method Post -ContentType 'application/json' -Body $pidBody
```

The response includes document/version UUIDs, filename, SHA-256, processed/duplicate
status, page/detection/region counts, equipment/instrument tags, manifest URI, and
warnings. An optional document_id attaches a new source revision to an existing
P&ID document. No natural-language answer is generated.

Only paths beneath the P&ID source directory are accepted. Absolute paths, parent
traversal, Windows alternate data streams, unsupported formats, mismatched image
extensions, encrypted PDFs, and malformed images are rejected. Limits are 20 MiB
per source, 10 PDF pages, 40 million pixels per page, and 120 million rendered
pixels per PDF. OCR limits are 5,000 detections per page and 20,000 per drawing.
This is a synchronous prototype, not a production upload/job service.

## Rendering, preprocessing, and coordinates

PDF pages render at 300 DPI by default, configurable from 300 to 400 in the request
or root `.env` using `PID_RENDER_DPI`. Image inputs retain original width/height,
DPI if present, format, and EXIF orientation in the manifest. Missing image DPI is
null rather than an invented value. PDF page size/rotation are recorded as well.

EXIF orientation is normalized into the stored rendered image. Optional explicit
0/90/180/270-degree rotation applies only to the separate preprocessing image.
OpenCV supports grayscale, CLAHE contrast normalization, optional median denoising,
and optional adaptive thresholding. Thresholding necessarily produces grayscale
output. Defaults avoid thresholding/denoising that could erase thin text strokes.
No automatic orientation or skew is inferred from pipe-like drawing lines.

The page manifest records an exact processed-to-rendered transform. OCR polygons
are mapped through it; every detection includes a pixel bbox/polygon, page number,
rendered image URI, and image dimensions. Coordinates use top-left origin and
refer to the stored rendered PNG, not the original PDF's point coordinate system.
Out-of-image boxes are rejected except for at most one pixel of boundary rounding.

Each detection preserves raw `text`, `normalized_text`, recognition confidence,
category, identified tags, bbox, polygon, page, source_image, and engine identity
`paddleocr_ppocrv5`. Every detection has `ocr_derived=true` and a status of
`unverified`, or `ambiguous` below recognition confidence 0.60. The API never emits
`verified`: pattern matching and confidence do not establish asset identity.
Low-confidence candidates remain visible with their raw text and a warning.
Zero detections return an explicit warning and empty results; no text is invented.

For example, the live fixture produced this detection (additional fields omitted):

```json
{
  "text": "P-101A",
  "normalized_text": "P-101A",
  "confidence": 0.9983885288238525,
  "bbox": [95, 127, 357, 191],
  "page": 1,
  "ocr_engine": "paddleocr_ppocrv5",
  "ocr_derived": true,
  "category": "equipment_tag",
  "status": "unverified"
}
```

## Identifiers and regions

Deterministic normalization handles Unicode width/dashes and whitespace around
recognizable identifiers. It never guesses ambiguous O/0 or I/1 substitutions.
Existing tag regexes are reused for equipment/instruments/line numbers. Categories
include equipment_tag, instrument_tag, valve_tag, line_number, temperature_value,
pressure_value, drawing_title, revision, and other_text. Valve control tags such
as FV-101 also remain in instrument_tags for compatibility. P&ID-specific patterns
extend the shared extractor with XV and NRV valve candidates without changing
Phase 3A extraction behavior. V-101 retains the
existing equipment classification; it is not assumed to be a valve symbol.

Regions group nearby OCR text within a page using text-height-scaled distance
limits and bounded group size/extent. Deterministic labels distinguish likely
equipment labels, instrument clusters, title blocks, and annotation blocks.
Region UUIDs, bboxes, raw text items, combined text, tags, and source image URI are
stored. Neither proximity nor a region type proves drawing semantics/connectivity.

## Artifacts, persistence, and duplicate behavior

```text
data/processed/pids/
  page_images/<version_uuid>/page_0001_rendered.png
  page_images/<version_uuid>/page_0001_processed.png
  ocr_json/<version_uuid>.json
  regions/<version_uuid>.json
  manifests/<version_uuid>.json
```

The manifest contains all source/document/version identities, SHA-256, page count,
render DPI, model names, pipeline version, UTC processing time, synthetic flag,
warnings, page metadata/transforms, counts, tags, and artifact URIs. JSON artifacts
use atomic file replacement. Raw source bytes are never written by the endpoint.

No schema migration is needed: the existing document_versions JSONB metadata and
string status fields store the request and `pid_processing`, `pid_processed`, or
`pid_failed` state. PostgreSQL checksum uniqueness and advisory transaction locks
protect duplicate/concurrent processing. Identical bytes plus identical metadata
and preprocessing settings return existing IDs/artifacts without rerunning OCR.
Missing artifacts can be regenerated on an identical request. Existing page images
are reused only when their decoded pixels match; a mismatch fails with the existing
file preserved. Neither rendered nor preprocessed images are overwritten on retry.
Conflicting metadata,
settings, document IDs, or a checksum registered in the Phase 3A text pipeline
return 409 and preserve the existing record. Failed requests are retryable with
the same inputs. Failed/partial processed artifacts may remain for diagnosis.

P&ID OCR is **not indexed in Qdrant in this phase**. The existing dense collection
and retrieval behavior are unchanged; `pid_processed` is distinct from `indexed`.
Access scope remains metadata only, not authorization. Existing health, query,
agent status, approval, audit, sovereignty, ingestion, and retrieval contracts are
preserved.

## Validation and limitations

```powershell
# backend/
.\.venv\Scripts\python.exe -m compileall -q app alembic scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m scripts.smoke_pid --fresh
.\.venv\Scripts\python.exe -m scripts.smoke_knowledge --fresh
```

The opt-in smoke test creates one small immutable synthetic image, runs real local
PaddleOCR through the API with PostgreSQL, validates tag/coordinate/artifact data,
checks duplicate IDs and original SHA-256, and verifies Qdrant's point count stays
unchanged. Its report lives in the ignored
`data/processed/pids/manifests/phase3b1_smoke_result.json`. Use `--trace` to emit
stack traces if first-start library initialization is unusually slow.
`--fresh` creates a separate tiny synthetic source and requires actual processing,
preventing a cached duplicate from being reported as a new OCR/ingestion run.
Both smoke scripts retain their original reusable-fixture behavior without the flag.
The model evaluation specification, cases, configuration and manifest are reference
assets only: this implementation does not modify them, train on them, or feed them
to OCR or a language model.

Small, rotated, low-contrast, overlapping labels and rasterized symbols remain
challenging. Recognition confidence is not proof of correctness. Human review
against rendered images is required before using OCR as operational evidence.
No automatic label-to-symbol assignment is performed.

Phase 3B2's precise scope has not been supplied. Deferred work includes any
approved OCR-text indexing/review extensions, sparse/BM25 retrieval and reranking;
multimodal reasoning, topology/connectivity, answer generation, agents, and sensors
remain separate later work. Nothing from those phases starts automatically.

Implementation references: [official PaddleOCR 3.3 usage](https://www.paddleocr.ai/v3.3.0/en/version3.x/pipeline_usage/OCR.html),
[official PaddlePaddle Windows installation](https://www.paddlepaddle.org.cn/documentation/docs/install/pip/windows-pip_en.html).
