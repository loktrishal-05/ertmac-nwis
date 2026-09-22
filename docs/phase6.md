# Phase 6 — P&ID evidence integration

## Implemented

P&ID OCR evidence integration into the existing agentic/RAG path.

The Phase 3B1 preprocessing, PaddleOCR, `OCRDetection`, `OCRRegion`, manifests,
and region artifacts are reused unchanged. Phase 3B2 retrieval finds relevant
drawing versions; the selective `pid_evidence_lookup` helper invokes the existing
registered `get_pid_regions` tool. No second OCR pipeline or agent was added.

Flow: existing drawing ingestion → indexed OCR evidence → scoped document
retrieval → region lookup → existing LangGraph specialist → typed answer and
drawing evidence → existing Phase 5 governance and evidence manifest.

## Evidence and citations

Drawing references carry document/version ID, source SHA-256, revision when
available, page, region ID, bounding box, source/image URI, raw OCR text,
separate normalized candidate, confidence, and `ocr_derived=true`.
The locator names the drawing, revision (or `unknown`), page, and region.
S3 tags reference these evidence IDs; S7/S4/S6 include supporting drawing
citations. Raw text is never overwritten with the normalized candidate.

The reader validates artifact/source containment, manifest-to-document/version
binding, actual source bytes, region count/uniqueness, raw text consistency,
and page range. Missing or malformed artifacts yield no drawing evidence.
Existing retrieval sufficiency and identifier-miss checks still apply.

## Agent and safety behavior

- Knowledge: explicit drawing/P&ID/OCR queries resolve retrieved versions to
  regions. The minimum answer path extracts labels deterministically.
- Confidence below 0.6 stays ambiguous, including a registry name match.
  High confidence alone remains unverified.
- Missing tags or requests to establish unreadable line sizes, isolation,
  valve state, or operational readiness return insufficient evidence.
- Returned OCR labels explicitly do not constitute a complete valve list.
- Safety: drawing evidence is supporting only; procedural evidence is required.
  OCR is excluded from the model's procedural evidence and action evidence basis.
  Existing S7 hardening and governance/HITL remain in force.
- Maintenance: OCR is excluded from diagnostic and threshold evidence. It may
  be attached as a supporting citation alongside other evidence; OCR alone
  cannot produce a diagnosis.
- Non-drawing queries do not invoke the region tool.

OCR never establishes topology, connectivity, flow direction, valve state,
physical isolation, permit status, or equipment readiness. This phase does not
interpret diagram geometry. Drawing evidence grants no authority or control.

## Phase 5D integration

New region evidence IDs include source hash, document version, region ID, and
a canonical hash of the structured region. The existing manifest stores raw
content and provenance including raw/candidate detections, confidence, geometry,
revision, image URI, and region hash. Before advisory release, Phase 5D reloads
the source and region artifacts and compares their hashes and provenance.
OCR or source mutation blocks release even after approval.

The existing ActionRevision, approval, manifest, audit chain, and release gate
are reused. Legacy references retain their prior handling and do not acquire
the new artifact-reverification guarantees retroactively. No database schema
change or second integrity system was introduced.

## Not implemented

- Verified knowledge cache or semantic answer cache
- Voice or multilingual support
- BI, fine-tuning, new agents, or n8n workflows
- Automatic plant control, SCADA/DCS writes, or equipment actuation
- Frontend changes or Phase 7 work

The deliberate minimum path extracts drawing labels; it does not infer pipe
sizes or complete equipment inventories from imperfect OCR. Existing retrieval
must first find the drawing. Live OCR/model quality is not established by the
synthetic integration fixtures; deployment still needs readable ingested drawings.
