# Phase 3B2 — Local hybrid evidence retrieval

This phase extends the existing document, version, BGE and Qdrant architecture.
It adds no answer generation, agents, LangGraph, model gateway, sensors, image
embeddings or process connectivity inference. The 75 model-evaluation cases and
their specification/configuration/manifest are unchanged and are not training data.

## Retrieval architecture

```text
query → normalize Unicode dashes/identifier spacing → detect identifiers
      ├─ BAAI/bge-base-en-v1.5 → dense top 30 (768, cosine)
      └─ local lexical encoding → Qdrant sparse top 30 (IDF)
          → deterministic RRF, sum(1 / (60 + rank))
          → optional local BAAI/bge-reranker-base on top 20
          → conservative duplicate/revision handling → final K citations
```

Both branches apply identical explicit metadata filters and PostgreSQL visibility
constraints. Only `indexed` and `pid_indexed` versions are searchable. Detected
identifiers strengthen sparse matching; they no longer automatically restrict
equipment/instrument filters. This avoids hiding incident or work-order evidence
that mentions an asset without complete tag metadata. Explicit filters remain hard
constraints. Dense-only and sparse-only modes are available for controlled comparisons.

RRF uses one-based ranks, contributes once per chunk per branch, and resolves score
ties by chunk UUID. Reranking orders its head by raw logit, then fusion score/UUID.
If K exceeds the reranked head, the remaining candidates retain fused order and a
null rerank score, with a warning. Results retain the legacy `score` field; its
meaning follows the selected strategy, so scores across strategies are not comparable.

## Sparse representation

`industrial-bm25-v1` is a deterministic BM25-style approximation with Qdrant's IDF
modifier, not canonical corpus-average-length BM25. Document weights are
`tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / 256))`. The fixed reference length
256 permits incremental indexing without rewriting the corpus when its average
length changes. Qdrant calculates IDF from the active collection, including points
outside a query's filters. Indexing has no neural model or network dependency.

Unicode normalization preserves whole hyphenated/slashed terms such as P-101A,
SOP-P204-001 and WO-7712. A small English stop list removes common query words.
Source text supplies frequency; missing title, section, revision and tag terms are
added once each, avoiding repeated boilerplate. Identifier-shaped query terms have
weight 3; other query terms have weight 1. No ambiguous O/0 or I/1 repairs occur.

Terms map to stable unsigned 32-bit BLAKE2s indices. Collisions are possible; this is
a bounded prototype representation and should be audited on a larger vocabulary.
There is no stemming, synonym expansion, or separate search engine.

## Explicit Qdrant migration

Qdrant server 1.17 rejects adding a previously absent sparse vector name to an
existing dense collection. The migration therefore uses a verified copy and alias:

```powershell
# backend/, stop external writers first
.\.venv\Scripts\python.exe -m scripts.reindex_sparse
# Inspect the reported copies and counts before promotion.
.\.venv\Scripts\python.exe -m scripts.reindex_sparse --promote
```

Preparation creates `knowledge_chunks_v1_dense_backup` and
`knowledge_chunks_v1_hybrid_v1`. It copies original IDs, payloads and dense vectors,
adds sparse vectors only to the hybrid copy, checks every copied payload/vector and
all point counts, and builds the existing metadata indexes. Nothing is deleted by
preparation. Promotion removes the original physical collection **only after those
checks**, then installs the `knowledge_chunks_v1` alias to the hybrid copy. The
dense backup remains intact. If alias creation fails, the code attempts to restore
the original name as an alias to the backup. A short maintenance interruption is
possible. Operators must retain the backup and inspect the alias after failures.

Both API ingestion and OCR indexing take a shared PostgreSQL advisory migration
lock; the CLI takes its exclusive counterpart. Other external Qdrant writers must
be stopped manually. Preparation/promotion is not a distributed transaction.

After promotion, rerunning the command only backfills missing/outdated sparse
vectors with `update_vectors`, preserving dense vectors and payloads except the
explicit `sparse_encoding` marker. Successful repeats report zero updates.
Normal ingestion writes both vectors. Sparse queries fail explicitly if eligible
points lack the current encoding marker; no partial sparse index is silently used.
New empty collections are created with both vector names from the start.

For rollback, stop writers and atomically repoint the `knowledge_chunks_v1` alias
to its dense backup using Qdrant's alias API, then disable sparse retrieval and
reranking. The backup contains only pre-migration points: new writes must be
reconciled before rollback. Neither the API nor startup deletes/recreates collections.

## Local reranker

```powershell
.\.venv\Scripts\python.exe -m scripts.download_reranker
```

Downloads the approved BAAI model's safetensors/tokenizer/configuration into
`models/bge-reranker-base`, recording its exact upstream revision. This is artifact
download only. Runtime uses Transformers `local_files_only=True`,
`trust_remote_code=False`, safetensors, evaluation mode and inference mode.
Model/tokenizer load lazily once per process; a lock protects prediction. Pairs
are batched in groups of 8. CPU works; CUDA is selected when available.

Scores are raw relevance logits, not confidence probabilities. Query/title/content
pairs are truncated to 512 tokens for scoring; citation content remains unchanged.
Disable reranking on weak CPUs or when artifacts are absent. An enabled missing
model produces an explicit dependency failure; no hosted fallback is called.

## Configuration

Root `.env` / environment settings:

| Variable | Default | Bounds / meaning |
| --- | --- | --- |
| SPARSE_RETRIEVAL_ENABLED | true | Enable sparse/hybrid queries |
| DENSE_TOP_K | 30 | 1–100 candidates |
| SPARSE_TOP_K | 30 | 1–100 candidates |
| HYBRID_FUSION | rrf | Only RRF supported |
| RERANKING_ENABLED | true | Enable local reranker |
| RERANKER_MODEL | BAAI/bge-reranker-base | Fixed approved model |
| RERANK_TOP_K | 20 | 1–100 candidates |
| FINAL_CONTEXT_K | 6 | 1–30; request may override |

Disabling sparse retrieval selects dense-only by default. Explicit requests for a
disabled strategy are rejected. No user request can supply a model name or path.

## API and citations

`POST /knowledge/retrieve` preserves `query`, `top_k`, nested `filters`, result
IDs/content/score and all original citation fields. `detected_identifiers` remains
a dictionary for backward compatibility, with `technical_identifiers` added.

```json
{
  "query": "P-101A abnormal vibration procedure",
  "top_k": 6,
  "strategy": "hybrid_rerank",
  "document_types": ["sop", "pid"],
  "filters": {"access_scope": "internal", "synthetic": true}
}
```

Strategy values: `dense`, `sparse`, `hybrid`, `hybrid_rerank`; omission uses server
settings. `top_k` is 1–30. Top-level equipment_tags, instrument_tags, facility_id
and unit_id are optional aliases for nested filters; contradictory values are
rejected. Document type lists are capped at 10 and tag lists at 30.

Responses add strategy, warnings, timings_ms, content_type, dense_rank, sparse_rank,
fusion_score and rerank_score. Citations add ocr_derived, ocr_confidence, region_id
and source_image_uri. Quotes, locations, source hashes and IDs come from stored
metadata; mismatched point/payload chunk IDs fail validation.

There is no calibrated relevance cutoff. Dense search can return unrelated nearest
neighbors for missing evidence. A lexical miss with an identifier emits a warning.
Returning evidence is not a factual answer or an assertion that an asset exists.

## OCR indexing

`POST /documents/pid/{document_version_id}/index` explicitly indexes an already
processed Phase 3B1 drawing. Processing alone continues to produce artifacts only.
The UUID endpoint reads validated local manifest/regions; verifies document/version
identity and original source SHA-256; and encodes useful region text with BGE and
sparse vectors. It does not write raw sources or rendered images.

Each chunk has stable version/region-based UUIDs, `content_type=pid_region_text`,
`document_type=pid`, page, region_id, bounding_boxes, tags, source filename/hash,
image URI, `ocr_derived=true`, and the minimum detection confidence in the region.
Confidence below 0.60 remains explicitly low-confidence in extraction_quality and
retrieval warnings. Raw OCR text supplies the quote. Coordinates remain rendered
image pixels, top-left origin; full-region boxes can span a split text chunk.

Existing DocumentVersion string states store `pid_indexing`, `pid_indexed` and
`pid_index_failed`; no Alembic migration is needed. Failures are hidden from
retrieval and retryable; duplicate indexing does not add points. Source processing
still recognizes indexed versions as completed OCR work.

**OCR-derived labels are evidence, not process topology.** No image embeddings,
symbol connections, flow directions, isolation plans or operational answers exist.

## Duplicate and revision policy

Duplicate chunk IDs collapse during fusion. Post-ranking deduplication removes
identical or at least 92%-similar text from the same source/version and section
when pages overlap. Numeric/tag tokens and negation changes prevent near-duplicate
collapse. OCR regions with different section IDs collapse only when their image
boxes substantially overlap; identical labels at distinct locations are retained.

For multiple candidate versions of one logical document, the unique latest
nonfuture effective_date is preferred only when every candidate version has a
known effective date. A warning names the preference and historical version filter.
Missing/tied/future dates retain distinct evidence with a conflict warning. Revision
strings and ingestion time alone are not proof of authority. Explicit version
filters override this preference. This policy only compares retrieved candidates;
the system has no company-wide approved-revision registry.

## Retrieval evaluation and live checks

```powershell
.\.venv\Scripts\python.exe -m scripts.prepare_retrieval_eval
.\.venv\Scripts\python.exe -m scripts.smoke_knowledge --fresh
.\.venv\Scripts\python.exe -m scripts.smoke_pid --fresh
.\.venv\Scripts\python.exe -m scripts.smoke_hybrid
.\.venv\Scripts\python.exe -m scripts.evaluate_retrieval
```

Run these sequentially: smoke checks compare global point counts, and inference
timings should not compete with another model-heavy process. Preparation reads
`retrieval_corpus.json`, creates 12 small synthetic PDFs through real ingestion and
one controlled low-confidence OCR fixture. That simulated OCR case tests uncertainty
handling and is explicitly separate from the real PaddleOCR smoke fixture.

`retrieval_questions.jsonl` contains 12 queries; `expected_citations.jsonl` supplies
graded expected source/page locators. The model benchmark is not used. Evaluation
filters the synthetic corpus by access_scope, compares all four strategies at K=3,
validates emitted citation data against stored points, and reports per-query and
category metrics: Recall, Precision, MRR, Hit Rate, nDCG and source/page hit accuracy.
Repeated source/page hits count once. Precision divides by K; missing-evidence cases
have null positive-relevance metrics and separate empty-result accuracy.

Results: `data/evaluation/results/retrieval_phase3b2.json`; live evidence:
`data/evaluation/results/phase3b2_live.json`. Both are local generated artifacts.
Timing fields measure embedding, dense search, sparse encoding/search, fusion,
reranking, deduplication and total request time in milliseconds. First-request timing
is recorded separately from warm per-query means. Dense's first request loads BGE;
the later hybrid modes reuse it. The first reranked request loads the reranker.
These first-request timings are not independent cold-start comparisons.
CPU/GPU results are not interchangeable.

## Limitations and sovereignty

No new dependency packages are required: Qdrant, Transformers, PyTorch and Hugging
Face download utilities already exist in the approved environment. Runtime search,
encoding and reranking are local. Initial model download requires internet access.
Access-scope filtering is preserved, but remains metadata, not authentication/RBAC.
Local filesystem ownership and controlled Qdrant writers remain trusted boundaries.

The small synthetic corpus can expose regressions but cannot establish general
retrieval superiority. Reranking benefit must be compared with its measured CPU cost.
Larger blind retrieval datasets, vocabulary collision audits, relevance calibration,
production authorization and scheduling remain future work. Phase 3C's exact
deliverables have not been specified; no Phase 3C implementation is included.

References: [Qdrant sparse vectors and IDF](https://qdrant.tech/documentation/manage-data/vectors/),
[BGE reranker model card](https://huggingface.co/BAAI/bge-reranker-base).
