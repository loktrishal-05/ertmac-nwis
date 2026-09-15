# Data conventions — Phase 3B2

Raw inputs are immutable. Place a new source revision in a new file; never edit
an ingested raw file. The ingestion API reads a byte snapshot and computes its
SHA-256; it never writes to `raw/`. The opt-in smoke script creates its synthetic
PDF only if it does not already exist.

```text
data/
  manifests/
    documents.csv
    equipment.csv
    tag_dictionary.csv
    dataset_licenses.md
  raw/
    sops/{source,metadata}/
    pids/{source,metadata}/
    incidents/{source,metadata}/
    maintenance/{work_orders,equipment_master}/
    sensors/{normal,faults,tag_dictionary}/
  processed/
    documents/{markdown,structured_json,page_images,extraction_reports}/
    pids/{page_images,ocr_json,regions,manifests}/
    maintenance/normalized/
    sensors/{normalized,windows,features}/
  indexes/
    qdrant_snapshots/
    ingestion_manifests/
  evaluation/
    retrieval_questions.jsonl
    expected_citations.jsonl
    model_eval_cases.jsonl
    model_eval_config.json
    manifest.json
    extraction_ground_truth/
```

Empty directories contain `.gitkeep`. CSVs remain templates. The retrieval question
and citation JSONL files now define the separate 12-query synthetic retrieval
benchmark; `retrieval_corpus.json` defines its source PDFs. Generated results live
under `evaluation/results/` and are Git-ignored. The model evaluation pack contains 75 reference cases
and model configuration; preserve it and `docs/model-evaluation-spec.md` unchanged.
Never use those evaluation assets for training or as OCR fixtures. Record dataset
sources, licenses, and permitted uses in `manifests/dataset_licenses.md` before import.

Phase 3A processes English native-text PDFs only. Its scanned/mixed PDFs remain
`ocr_required` and are not indexed. The separate Phase 3B1 endpoint accepts
PDF/PNG/JPG/JPEG only under `raw/pids/source`, producing rendered/preprocessed
pages, OCR JSON, regions, and manifests under `processed/pids`. These artifacts
can be explicitly indexed as OCR text using the Phase 3B2 version-index endpoint.
Processing alone remains artifact-only. Sensor/maintenance processing remains unimplemented.
OCR and spatial proximity do not establish process topology or connectivity.

Processed Markdown, parser JSON, and extraction reports are named by the
PostgreSQL document-version UUID. Ingestion manifests contain the exact validated
chunk payloads and model identity. Page references are 1-based; bounding boxes
include their coordinate origin and describe source blocks, not precise character
spans. Raw/processed files, model artifacts, snapshots, and runtime manifests are
Git-ignored. Commit only directory markers, this guide, manifest templates, and
small curated evaluation definitions. Do not put secrets in those tracked files.
