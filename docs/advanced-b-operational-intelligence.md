# Advanced-B operational intelligence

Advanced-B extends the existing local graph, evidence ledger, human review and
Workspace. It does not grant plant execution authority. No new dependency,
hosted model, benchmark prompt or benchmark interface is introduced.

## Handover and tacit knowledge

Authenticated users can record equipment-linked operator notes. Authorship and
creation time come from the server. Notes remain human reports, including after
review; they are not verified engineering truth. The existing Approvals workflow
reviews the immutable proposal and evidence snapshot. Rejected, revoked,
expired or changed notes cannot be reused as current reviewed evidence.

Shift handover assembles sensor readings, maintenance records, SOP evidence,
operator notes and incident descriptions for a registered equipment tag and an
explicit timezone-aware period of at most 72 hours. Observations, human reports,
completed/ongoing maintenance, unresolved questions and citations remain separate.
Synthesis is deterministic; model synthesis and hypotheses are empty rather than
invented. Safety-state claims in narrative reports are withheld for field review.
Incident closure and equipment readiness are never inferred from these records.

## Environmental comparison

A stored sensor reading is compared with explicit local rule IDs from the
existing verified-knowledge registry. Rules must be human-reviewed, current,
source-bound JSON statements. Example shape (illustrative, not a real limit):

```json
{
  "parameter": "example_parameter",
  "unit": "mg/L",
  "equipment_tag": "P-101A",
  "upper_limit": 5,
  "valid_from": "2026-01-01T00:00:00Z",
  "valid_to": "2027-01-01T00:00:00Z",
  "averaging_period": "instantaneous"
}
```

The exact statement must occur in its reviewed source quote. Parameter,
equipment, unit, reading timestamp, finite values and measurement quality are
checked. Missing, revoked, stale, incompatible or conflicting rules yield
`INDETERMINATE`. Otherwise the result is `WITHIN_DOCUMENTED_LIMIT` or
`EXCEEDS_DOCUMENTED_LIMIT`. This is a local documented-limit comparison, not
legal certification; no statutory limits are supplied or inferred.

## Knowledge gaps and visual evidence

Gap detection combines source sufficiency, missing operational evidence and OCR
uncertainty. Gaps have stable IDs, severity, required information, evidence links
and OPEN status. They are persisted in existing execution metadata and audited.
Metadata uses equipment identifiers or query hashes, not raw query text.
The gap API deduplicates the latest 100 stored execution records by creation time.
It does not resolve gaps, close incidents or establish completeness.

P&ID label answers preserve raw OCR, normalized candidates, confidence,
bounding boxes, document/version/hash/region identity and supplied revision.
Ambiguous or conflicting candidates remain unresolved; human-verified label and
model interpretation fields remain empty. Missing revisions and conflicting OCR
produce gaps. OCR cannot establish connectivity, field valve state, isolation,
permit validity or readiness. The existing visual query path remains the entry
point; the Workspace displays its evidence and limitations.

## APIs and routing

| Endpoint | Input / result |
| --- | --- |
| `POST /operator-notes` | Equipment tag, optional unit and text; server-authored record and approval revision |
| `GET /operator-notes?equipment_tag=...` | Latest 100 equipment notes, live review state and human-report trust label |
| `POST /shift-handover` | Equipment tag, aware `start` / `end`; governed query response |
| `POST /environmental-compliance` | Reading UUID and up to 10 reviewed rule UUIDs; governed comparison |
| `GET /knowledge-gaps` | Deduplicated gaps from stored runs |

All endpoints require an authenticated requester, reviewer or admin. Review
authority stays with existing reviewer/admin checks and separation of duties.
Only internal scope is supported; client authorship and verification fields are
rejected. Records are shared within that existing internal role scope, not
partitioned by owner or tenant.

The operational forms call the common `/query` boundary using validated
`OPERATIONAL_CONTEXT` JSON. Preflight remains active. Deterministic operational
routing selects the existing agentic path and LangGraph specialists, bypassing
adaptive document synthesis and model route generation. Free-text requests
without explicit context receive clarification. Authentication also applies to
operational replay. Other requests keep existing adaptive routing.

Handover and comparisons are pending advisory drafts. Human review, manifest
binding, release/revocation and audit use the existing governance services.
Audit vocabulary adds OPERATOR_NOTE_CREATED, HANDOVER_GENERATED,
COMPLIANCE_ASSESSMENT_GENERATED, KNOWLEDGE_GAPS_IDENTIFIED and
VISUAL_INTERPRETATION_REQUESTED. These events never authorize plant actions.

## Deployment and limits

Migration `0013_operational_intelligence` follows `0012_knowledge_packs`. It adds
operator notes and extends evidence/audit constraints. Existing immutable
ledger tables and protections remain in use. A downgrade refuses when new
immutable evidence or audit types exist; it must not silently discard them.

The compact Operational Intelligence page supplies handover, compliance, notes
and gaps. Approval decisions remain on the Approvals page. Switching forms
clears old results to avoid presenting a handover as a compliance result.

Handover reads at most 200 sensor rows and 100 each of maintenance, notes and
incidents. It does not guarantee interval coverage. Recent advisories lack a
reliable equipment link and are not automatically merged. Environmental rules
support instantaneous upper bounds only, with exact units and no conversion.
Visual intelligence extracts labels, not geometry or independently verified
title blocks. There is no autonomous tacit-knowledge promotion, gap-resolution
workflow, live telemetry certification or plant write tool. Source checks are
not a distributed snapshot across database, files and retrieval storage.
