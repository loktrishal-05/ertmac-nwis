# Data conventions — Phase 3A

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
    extraction_ground_truth/
```

Empty directories contain `.gitkeep`. CSVs are header-only templates; evaluation
JSONL files have no records. Record dataset sources, licenses, and permitted uses
in `manifests/dataset_licenses.md` before import. No external datasets are included.

Phase 3A processes English native-text PDFs only. P&ID, sensor, page-image, and
maintenance directories reserve the approved structure; they do not imply those
pipelines are implemented. Scanned or mixed PDFs requiring OCR are marked
`ocr_required` and are not indexed.

Processed Markdown, parser JSON, and extraction reports are named by the
PostgreSQL document-version UUID. Ingestion manifests contain the exact validated
chunk payloads and model identity. Page references are 1-based; bounding boxes
include their coordinate origin and describe source blocks, not precise character
spans. Raw/processed files, model artifacts, snapshots, and runtime manifests are
Git-ignored. Commit only directory markers, this guide, manifest templates, and
small curated evaluation definitions. Do not put secrets in those tracked files.
