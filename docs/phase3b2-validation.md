# Phase 3B2 validation report

Validated locally on 2026-09-15. Phase 3B2 is implemented. No Phase 3C, answer
generation, agents, LangGraph, Qwen/Ollama backend integration, sensor processing,
image embeddings or topology reconstruction was added.

## Implementation and dependencies

- Dense model remains BAAI/bge-base-en-v1.5, 768 dimensions, cosine distance.
- Qdrant sparse vectors use a local identifier-preserving BM25-style term-frequency
  representation with live Qdrant IDF. Fixed reference document length is 256;
  this is an approximation, not canonical corpus-average-length BM25.
- RRF sums `1 / (60 + rank)` across dense/sparse candidate lists, with stable UUID
  tie breaking and one contribution per branch per point.
- Optional BAAI/bge-reranker-base runs locally in batches of 8; lazy model reuse,
  CPU/CUDA selection, local-only artifacts, raw logit scores and 512-token pair limit.
- Reranker artifact revision: `2cfc18c9415c912f9d8155881c133215df768a70`.
- No new dependency packages were needed. Existing Qdrant client 1.17.1,
  Transformers, PyTorch and Hugging Face utilities support these additions.
  Validation used PyTorch 2.14.0+cpu with 8 threads on Windows/Intel CPU.
- No database migration: existing version string states and JSONB metadata suffice.
- Added settings: SPARSE_RETRIEVAL_ENABLED, DENSE_TOP_K, SPARSE_TOP_K,
  HYBRID_FUSION, RERANKING_ENABLED, RERANKER_MODEL, RERANK_TOP_K, FINAL_CONTEXT_K.

## Collection migration and preservation

The installed Qdrant 1.17 server rejected an in-place addition of a new sparse
vector name with HTTP 400. Preparation copied and verified all 3 existing points
into a full dense backup and a hybrid collection. After explicit approved
promotion, `knowledge_chunks_v1` resolves as an alias to
`knowledge_chunks_v1_hybrid_v1`. `knowledge_chunks_v1_dense_backup` retains the
original physical data. No source document was deleted or modified.

Validation checked original IDs, every payload field and dense vector values
(tolerance 1e-6). The hybrid collection retains existing metadata indexes and adds
the named `sparse` vector with IDF. Subsequent explicit backfill reported **zero
updated points**, proving repeat idempotence. Ingestion writes both vector names.
See the implementation guide for maintenance locks, promotion interruption and
rollback limitations; the backup predates new writes and is not a current replica.

## API and OCR evidence

`POST /knowledge/retrieve` retains legacy fields and adds strategy, ranks, scores,
timings, warnings and OCR citation metadata. Explicit scope/type/asset/location
filters apply to both branches. Automatic identifier extraction strengthens
lexical matching without the old implicit asset-only exclusion. K is limited to 30.

`POST /documents/pid/{document_version_id}/index` indexes existing stored OCR regions
after source SHA-256 and artifact identity checks. Stable chunk UUIDs prevent
duplicate points; `pid_indexed` controls retrieval visibility. Low confidence remains
visible. Artifact-only OCR processing behavior is preserved until explicit indexing.

Live indexing of fresh real OCR version `b647b164-0a87-4671-96c1-9ba5fa2f7f79`
added **6 region chunks** (collection count 17 → 23). Repeating the endpoint returned
`duplicate` with 6 chunks and no count change. Queries P-101A, TT-101, FV-101,
"pump abnormal vibration procedure", and "P&ID region containing P-101A" ran
through dense, sparse, RRF, and real reranking. OCR results included region IDs,
source hashes, page-one image-pixel boxes, confidence and exact stored quotes.
All **32 existing raw files** retained their SHA-256 values during this live check.

Live result: `data/evaluation/results/phase3b2_live.json`.

## Retrieval evaluation dataset

Independent synthetic diagnostic set:

- `retrieval_corpus.json`: 12 text documents, materialized as tiny native PDFs and
  ingested through real Docling/BGE/Qdrant.
- One additional controlled OCR fixture with recognition confidence 0.54. This is
  explicitly simulated OCR for uncertainty handling, not a real OCR accuracy claim.
- `retrieval_questions.jsonl`: 12 questions (11 with evidence, 1 missing identifier).
- `expected_citations.jsonl`: graded source/page relevance judgments.
- Queries cover equipment/instrument/valve tags, SOP sections, maintenance and
  incident references, rare identifiers/acronyms, natural language, multi-document
  evidence, ambiguous OCR and missing evidence.

No case, configuration, specification or manifest from the existing 75-case model
benchmark was modified. The retrieval benchmark is not used for training.
Evaluation isolates its corpus with `access_scope=synthetic-retrieval-eval` and
`synthetic=true`; Qdrant's IDF statistics still cover the full active collection.

## Metrics and comparison

Source/page-level metrics at **K=3**; repeated source/page hits count once.
Positive metrics average the 11 answerable queries. Precision divides by K, so
one relevant source among three returned sources contributes 1/3. Missing evidence
is excluded from positive metrics and scored separately for empty-result behavior.
These are retrieval metrics, not generated-answer correctness or safety scores.

| Strategy | Recall@3 | Precision@3 | MRR | Hit Rate@3 | nDCG@3 | Source/page hit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dense only | 1.000 | 0.364 | 1.000 | 1.000 | 1.000 | 1.000 |
| Sparse only | 1.000 | 0.364 | 0.955 | 1.000 | 0.959 | 1.000 |
| Dense + sparse RRF | 1.000 | 0.364 | 1.000 | 1.000 | 1.000 | 1.000 |
| RRF + BGE reranker | 1.000 | 0.364 | 1.000 | 1.000 | 1.000 | 1.000 |

Sparse-only placed the expected abnormal-vibration source second on RET-001;
dense, hybrid and reranked retrieval put the expected source first. All other
positive cases had the expected first source at rank one in every strategy.
All required sources for the multi-document case appeared within K.

For missing identifier ZZQ-99999, sparse returned no evidence (empty-result
accuracy 1); dense, hybrid and reranked modes returned neighbors (accuracy 0).
There is no calibrated rejection threshold. Hybrid output warns about its lexical
miss; it does not claim the missing equipment exists.

**This benchmark does not demonstrate hybrid superiority over dense retrieval.**
RRF matched dense and recovered sparse's one first-rank miss. Reranking added no
measured quality benefit on this small set. Larger and harder blind retrieval
judgments are needed; the perfect scores are not a production-quality claim.
The dense comparison is a Phase 3B2 ablation with the same explicit filters and
deduplication, not a replay of Phase 3A's former implicit asset-filter policy.

Machine-readable complete result, dataset hashes, per-category/per-query rankings,
citation validation and model revision: `data/evaluation/results/retrieval_phase3b2.json`.

## Performance

Warm mean milliseconds over 12 queries, on CPU, with no concurrent indexing/model
work during evaluation. Total includes PostgreSQL readiness and Qdrant configuration
checks, so it exceeds the sum of the listed inference/search stages.

| Stage | Dense | Sparse | RRF | RRF + reranker |
| --- | ---: | ---: | ---: | ---: |
| Dense embedding | 36.95 | 0 | 40.93 | 42.16 |
| Dense search | 17.10 | 0 | 15.68 | 11.33 |
| Sparse encoding/search | 0 | 31.28 | 22.82 | 19.92 |
| Fusion | 0.03 | 0.03 | 0.04 | 0.04 |
| Reranking | 0 | 0 | 0 | 844.39 |
| Total | 83.13 | 63.35 | 102.35 | 947.25 |

Reranking cost about **845 ms extra per query**, approximately **9.3×** the hybrid
total, with no measured quality gain here. It remains optional; the requested
default is enabled, and weak CPU deployments can set RERANKING_ENABLED=false.

First dense request including model load: 8.82 s. First reranked request including
reranker load: 5.13 s. These are first-use observations in one process, not
independent cold-start comparisons: later strategies reuse loaded BGE.
Pair truncation, CPU scheduling and corpus size affect timings; GPU was not tested.

## Regression and validation commands

| Check | Result |
| --- | --- |
| Python compileall | Passed |
| Backend tests | 50 passed: 37 previous + 13 hybrid tests |
| pip check | No broken requirements |
| Alembic check | No new upgrade operations detected |
| Docker Compose config | Passed |
| PostgreSQL pg_isready | Accepting connections |
| Qdrant healthz | Passed |
| Frontend npm run build | Passed after approved sandbox subprocess retry |
| Frontend npm run lint | Passed |
| git diff --check | Passed |
| Fresh Phase 3A ingestion/retrieval | Passed with real Docling, BGE, Qdrant and reranker |
| Fresh Phase 3B1 OCR | Passed with real PaddleOCR CPU |
| Real sparse/hybrid/reranker API smoke | Passed |
| Protected model benchmark | Hashes and Git contents unchanged |

Fresh Phase 3A version `e4a03ec2-b83b-499d-88b4-4df4efb545fa` produced one Docling
chunk with no warnings. Real 768-dimensional unit-normalized BGE vectors and
page-one source/hash/quote/box citations passed. Duplicate ingestion and source
immutability passed. Its ignored report remains under `indexes/ingestion_manifests`.

Fresh Phase 3B1 CPU OCR took **35.24 seconds**, produced **8 detections / 6 regions**,
and recognized P-101A, V-101, E-101, TT-101, PT-101, FV-101. Source SHA-256:
`3d300cf4f208d381a29a5e1f5d89bb8b5789eed656586df0c31a24b0030395b3`.
Processing itself added no Qdrant points; explicit indexing happened afterward.

An earlier OCR smoke attempt overlapped corpus ingestion and its global point-count
assertion failed because the corpus added points. The smoke was rerun successfully
after writes completed. Validation scripts should run sequentially. This was not
an OCR fallback or a fabricated OCR success.

Commands are documented in the implementation guide. Unit tests cover sparse
encoding/search/backfill, RRF ties/duplicate IDs, explicit scope filters, bounded
requests, reranker enable/disable/scoring/batches, revision preference/conflicts,
near duplicates/numeric/negation changes, overlapping OCR regions, low confidence,
schema round trips and known metric calculations. Existing tests remain intact.

## Files created

- `backend/app/services/sparse.py`
- `backend/app/services/ranking.py`
- `backend/app/services/reranking.py`
- `backend/app/services/pid_indexing.py`
- `backend/app/services/retrieval_metrics.py`
- `backend/scripts/download_reranker.py`
- `backend/scripts/reindex_sparse.py`
- `backend/scripts/prepare_retrieval_eval.py`
- `backend/scripts/evaluate_retrieval.py`
- `backend/scripts/smoke_hybrid.py`
- `backend/tests/test_hybrid.py`
- `data/evaluation/retrieval_corpus.json`
- `docs/phase3b2.md`
- `docs/phase3b2-validation.md`
- Ignored local model weights, tiny raw/processed validation fixtures and two
  machine-readable Phase 3B2 result files.

## Files modified

- `.env.example`, `.gitignore`, `README.md`, `backend/README.md`, `data/README.md`
- `backend/app/core/config.py`
- `backend/app/schemas/knowledge.py`
- `backend/app/api/routes/pid.py`
- `backend/app/services/ingestion.py`
- `backend/app/services/pid_processing.py`
- `backend/app/services/qdrant_service.py`
- `backend/app/services/retrieval.py`
- `data/evaluation/retrieval_questions.jsonl`
- `data/evaluation/expected_citations.jsonl`

## Limitations and remaining Phase 3C scope

**OCR-derived labels are evidence, not process topology.** Sparse hashing can
collide; BM25 uses a fixed reference length; IDF is collection-wide; reranker scores
are uncalibrated and use truncated text pairs. Near-duplicate detection and candidate
revision selection are conservative heuristics. Missing-evidence rejection remains
unresolved for dense/hybrid modes. Access scope remains filtering, not RBAC.

The model download required an approved network retry. Git line-ending notices,
Starlette TestClient deprecation, and Paddle's ccache/oneDNN messages were nonfatal.
GPU behavior is implemented but untested. Migration promotion has a short maintenance
window; operators must stop external writers and retain/reconcile the dense backup.

The exact Phase 3C task specification is not present in the request or repository.
Therefore no exact approved Phase 3C implementation list can be asserted. It needs
a separate scope defining its data, APIs, evaluation gates and authorization
boundaries. No excluded sensor, orchestration, model-gateway or topology feature
was inferred or started automatically.
