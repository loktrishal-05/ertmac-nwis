# B1 local multimodal P&ID intelligence

## Architecture

The existing `/documents/pid/process` path renders PDF pages with PyMuPDF or validates
PNG/JPEG images, preprocesses locally, and runs local PaddleOCR. Optional local vision
adds typed candidate observations on the rendered image. Docling remains the existing
document extraction path; no second application or hosted extraction service is added.

OCRRegion, PIDManifest and PIDRegionEvidence now retain visual candidates. The existing
P&ID index produces candidate text in Qdrant under the same source/version/region IDs.
Visual-only regions can be indexed. Existing retrieval and `get_pid_regions` expand
citations into current region evidence; the Knowledge/LangGraph drawing path returns
OCR, visual candidates, deterministic fusion, revision, provenance and citations.
No model generates the final drawing answer: it is a bounded evidence listing or refusal.

## Local adapter and configuration

`VisionAdapter` is an injectable protocol; `LocalVisionAdapter` implements Ollama
`/api/tags`, `/api/show` and `/api/chat`. It checks installation and vision capability,
validates image dimensions and output bounding boxes, and rejects remote model metadata.
There is no model download or hosted fallback. Redirects and environment proxies are
disabled. Existing MODEL_BASE_URL and MODEL_ALLOWED_HOSTS locality/denylist checks apply;
DNS must resolve exclusively to loopback/private addresses before dispatch. Existing
network controls remain necessary against DNS rebinding and misconfigured private proxies.

Configuration (server-owned environment, not request fields):

```
PID_VISION_ENABLED=false
PID_VISION_MODEL=qwen3.5:9b
PID_VISION_TIMEOUT_SECONDS=60
MODEL_BASE_URL=http://127.0.0.1:11434
MODEL_ALLOWED_HOSTS=127.0.0.1,localhost,::1,ollama
```

Vision is opt-in. Unsupported runtime, missing model, timeout, invalid output or invalid
image artifact produces explicit unavailable metadata and OCR-only safe fallback.
Each HTTP request is bounded by the configured timeout. No confidential source leaves
the configured local/private runtime. The adapter bounds page output to 100 candidates.

## Fusion and registry authority

OCR and visual confidence remain separate; no combined score is calculated. Candidate
types include symbols, labels, arrows, line fragments, title blocks and annotations.
Only single recognized tag strings and enumerated uncertainty categories are accepted;
free-form model operational claims and authority fields are rejected.

Overlapping bounding boxes associate observations as candidates only. This is not a
claim that a nearby label belongs to a symbol or that two pipes connect.

| Evidence | Identity status |
|---|---|
| High OCR, no conflict, current authoritative registry definition | VERIFIED |
| Low OCR, even with visual agreement and registry support | CANDIDATE |
| Visual-only candidate | UNVERIFIED |
| OCR/visual disagreement or registry mismatch | CONFLICTING |
| No candidate evidence | UNKNOWN |

Equipment rows can be auto-created during ingestion, so presence alone is not authority.
Verification requires an exact registry row plus exactly one current VERIFIED knowledge
record for `what is the documented definition of TAG?`. Existing Verified Knowledge
refresh rechecks source revisions, hashes and human approval. Registry and reviewed
source IDs are preserved in fusion provenance. Missing or conflicting registry evidence
requires review. Verified identity means a documented tag, never current equipment state
or a verified association between that tag and image geometry. Visual-only results stay
unverified even with a matching registry definition.

## Provenance and revisions

Every returned region binds document ID, version/revision, page, rendered image URI,
region ID, bounding box, source SHA-256 and canonical region hash. Raw and normalized
OCR, recognition confidence, visual model/candidates and fusion authority are retained.
Origins distinguish OCR, VISUAL_MODEL, REGISTRY, DOCUMENT_METADATA and HUMAN_VERIFIED.
Canonical evidence integrity includes visual observations and fusion provenance. Legacy
OCR artifacts retain their original canonical hash and approval provenance; fusion is
not retroactively attached to old frozen evidence.

Changed source bytes or any newer document version invalidate prior region reads.
Historical artifacts are retained. Registry authority is rechecked at read time;
revocation or changed reviewed sources also changes evidence integrity.

## Safety, routing, sufficiency and human review

Imagery alone cannot prove topology, process connectivity, flow direction, valve
open/closed state, isolation, LOTO, permit state, startup/shutdown readiness,
safe-to-operate state or process readiness. The drawing response path deterministically
refuses these requests; the model has no authority/status output fields or plant tools.
Other agents retain existing evidence, safety and governance gates.

P&ID/visual reasoning, low OCR confidence and conflicting evidence select the A1 deep
qwen3.5:9b policy. Bounded visual extraction uses the configured local vision model;
it never supplies verification authority. 4B cannot become authoritative for imagery.
Visual confidence does not establish sufficiency. Unverified visual identity is PARTIAL
even with a perfect visual score; existing SUFFICIENT/PARTIAL/INSUFFICIENT coverage
measurement and source checks still apply.

Low OCR, ambiguous identity, conflicts and missing authority set the existing
human_approval_required state and create existing knowledge-gap review recommendations.
Safety interpretations are refused and require review. Stale revisions fail closed.
No separate approval system is introduced.

## Persistence and observability

Processing reuses DocumentVersion ingestion lifecycle, PostgreSQL advisory locks,
atomic artifact writes and completed-manifest duplicate detection. Retrying persisted
completed processing does not repeat OCR or vision, including after process restart.
This checkout has no A2 LangGraph checkpointer. No second checkpoint system is added.
A crash before the final manifest/database commit may repeat unfinished processing;
per-page resume is not implemented. Enabling vision does not silently reprocess a
completed OCR-only version; existing immutable duplicate semantics are retained.

The manifest records document/revision, region counts, calls, model, latency and
fallback reasons. Processing verification/conflict counts are zero because registry
fusion occurs on read; query metadata reports actual fused candidate/verified/conflict
counts. No prompts, images or hidden reasoning are written to operational logs.

## Testing and limitations

`tests/test_multimodal_pid.py` covers deterministic fusion, registry authority,
revision invalidation, prohibited operational claims, provenance, unavailable/hosted
runtime behavior, sufficiency, ambiguity, malformed images, compatibility, routing,
completed-processing reuse and visual retrieval contracts. All unit images are synthetic;
model calls use httpx MockTransport. Existing P&ID, hybrid retrieval, evidence integrity,
security, routing and backend suites must also pass.

Local live validation used only a newly created synthetic drawing and the installed
qwen3.5:9b. The initial 60-second call safely timed out. A retry with a 180-second
timeout returned two schema-valid, uncertain regions in 63.3 seconds, with no tag
identified. This was a successful adapter/provenance protocol test, not a successful
tag-reading accuracy test. A successful protocol run does not benchmark symbol-recognition accuracy.
No frozen benchmark artifacts are used or modified, and BLIND is not rerun.
Region retrieval uses textual descriptions of visual candidates with existing hybrid
RAG, not a new visual embedding index. Dense P&IDs, tiny labels and ambiguous geometry
require human inspection. There is no field verification, control capability or safety
certification. The system supplies evidence for existing review, never plant permission.

## Validation result (2026-09-28)

- Confirmed imports resolve from `sovereign-multimodal-pid/backend/app` using the
  shared `sovereign-agentic-workbench/backend/.venv/Scripts/python.exe` interpreter.
- Final B1 tests: 27 passed, zero failures/errors/skips.
- Targeted regression run: 299 tests, 276 passed and 23 skipped; the final B1
  ambiguity-review regression was also validated separately and in the full suite.
- Final full backend run: 743 tests, 697 passed, zero failures, zero errors,
  46 skipped (opt-in PostgreSQL/live-model tests).
- Local live vision protocol: PASS on a synthetic image; details and accuracy
  limitations are recorded above.
- `git diff --check`: clean. Benchmark and frontend files unchanged. No hosted AI,
  plant-write tools, new dependencies, automatic model downloads or commit added.

Reproduce from this worktree's `backend` directory in PowerShell:

```powershell
$env:MODEL_NAME = 'qwen3.5:9b'
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Users\Lohith k\Desktop\sovereign-agentic-workbench\backend\.venv\Scripts\python.exe' -m unittest discover -s tests -p test_multimodal_pid.py -v
& 'C:\Users\Lohith k\Desktop\sovereign-agentic-workbench\backend\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

The full suite needs permission to write the existing sensor test's generated
artifact under this worktree's data directory. Initial validation exposed and
fixed a legacy citation wording regression; the final run above includes that fix.
