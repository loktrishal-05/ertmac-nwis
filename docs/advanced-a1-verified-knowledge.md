# Advanced-A1 verified knowledge foundation

## Architecture and authority

PostgreSQL remains the lifecycle and authorization authority; Qdrant remains the document chunk store. A1 adds `verified_knowledge` above existing ingestion, citations, immutable governance revisions, approval decisions, evidence manifests and the tamper-evident audit chain. No model, embedding service or replacement database is introduced.

Candidates reference existing chunk UUIDs. The server resolves evidence from Qdrant and PostgreSQL; clients cannot supply quotations, hashes, reviewer identity or trust state. Only authenticated requester/reviewer/admin accounts may create/read internal records. Only the existing reviewer/admin roles may verify, stale or revoke. Server-side authorization reloads the role from SQL with autoflush disabled. Account authentication remains the existing session-cookie mechanism; no client role or LLM claim confers authority.

Creation builds an immutable, human-review-required S1 proposal through `create_revision`, binding the complete knowledge content and source snapshots. It appears in the existing approval queue. Verification calls the existing `apply_decision` service and release-integrity gate: different reviewer, exact revision/hash, authoritative role, source integrity and approval validity are enforced. Verification then records reviewer and timestamp. An approval entered through the existing approval API alone does not promote a candidate; the registry verification operation is still required. This is one shared approval ledger, not another approval system. Verification permits reuse of an informational statement, never equipment operation.

## Schema and lifecycle

Migration `0011_verified_knowledge` adds the registry table and extends the existing audit event-type CHECK constraint. It preserves chain hashing and immutable audit triggers.

Each record includes a knowledge UUID, title, question, exact-match key, statement, existing EvidenceRef snapshots, document/version/revision identifiers, source and chunk hashes, bound content hash, internal access scope, created/updated/verified timestamps, creator/reviewer, approval revision ID and lifecycle status. A new content revision creates a new candidate UUID with `supersedes_id` and incremented revision number; old content is retained. No update-in-place content endpoint exists. Multiple verified matches are deliberately ambiguous and fall back until obsolete records are retired.

- CANDIDATE: never a trusted fast-path answer.
- VERIFIED: requires authorized human approval plus current source state.
- STALE: not served; create a fresh candidate and obtain new review.
- REVOKED: terminal for that record; never served.

## Invalidation

Every registry inspection/list and every potential trusted lookup re-resolves sources. The service compares the immutable proposal binding, local source bytes, document/version hashes and lifecycle, revision metadata, chunk content/metadata, and access scope. Missing/changed/revoked evidence or newer document revisions make the record STALE with an audit event. Existing approval expiration or revocation also prevents reuse and stales the record. Direct source edits are detected on access; A1 does not claim background push invalidation. Qdrant/SQL outages fail closed for the fast path and fall back to the existing agentic path; they never create trust.

Checks reflect source state at resolution time. PostgreSQL and Qdrant/filesystem are not one distributed transaction; an external out-of-band mutation after a completed read cannot be made atomic across stores. Existing approval release/revoke locking is reused before serving. Human verification establishes a reviewed statement, not scientific truth or current plant state.

## Query execution

Existing authentication dependency and current deterministic preflight (scope, injection, unsafe action, company domain) run before lookup. Idempotent governed-draft replay retains its existing behavior. Authenticated internal requests then qualify only for conservative static documented-fact lookup: the supported question grammar asks for a documented limit, threshold, rating, unit or definition for/of one identifier. Other wording falls back. Matching uses case folding and collapsed whitespace while preserving punctuation, numbers and identifiers; no semantic similarity search promotes trust.

Only one current VERIFIED match may be returned. Unknown, dynamic, safety/action, ambiguous, stale, revoked, unauthorized or unavailable cases fall back to the existing LangGraph/RAG path. Successful hits still enter `govern_response`, so verification never suppresses HITL or safety requirements. Informational responses retain existing evidence/citations and add `knowledge_lookup` metadata identifying VERIFIED_FAST_PATH or EXISTING_AGENTIC_PATH, source revisions, verification timestamp and fallback reason where relevant. Governed draft bodies remain unchanged for idempotent replay; path metadata is logged separately. Logging contains no chain-of-thought.

A1 deliberately supports only non-OCR indexed document chunks and the existing internal scope. P&ID OCR, sensor windows, live valve/isolation claims, expanded access scopes, and semantic matching are excluded from trusted lookup. This is a safe initial coverage limit, not independent proof of OCR or field state.

## APIs

- POST `/verified-knowledge`: create candidate from title, question, statement, chunk_ids, optional supersedes_id, internal scope.
- GET `/verified-knowledge?q=...`: list up to 100 internal items, optionally exact normalized-question search; refresh trust before display.
- GET `/verified-knowledge/{knowledge_id}`: inspect content, evidence, verification and provenance.
- POST `/verified-knowledge/{knowledge_id}/verify`: reviewer/admin verification using expected_content_hash and review comment.
- POST `/verified-knowledge/{knowledge_id}/stale`: reviewer/admin retirement as stale.
- POST `/verified-knowledge/{knowledge_id}/revoke`: revoke knowledge and revoke/reject the bound approval where applicable.

All endpoints require authentication; mutation payloads forbid extra fields. `expected_content_hash` detects stale reviewer screens but is not authorization. Existing `/approvals` APIs remain available for review detail and reject/revoke decisions. All authoritative registry mutations and audit entries share a transaction; audit failure prevents commitment.

## OKF-compatible adapter/representation layer

No verified OKF specification/version was found in repository documentation. This is **OKF-compatible adapter/representation layer**, not certified external compliance. Application-owned adapter version `a1-v1` maps identity/content, evidence/source revisions, lifecycle, trust, timestamps, scope and provenance into a JSON representation independent of ORM columns.

`export_item` is the mapping API used by registry endpoints. `import_candidate` accepts that representation and returns a candidate input; imported trust, hashes, timestamps and reviewer claims are ignored. Call `create_candidate` as an authenticated account to re-resolve all source UUIDs and create fresh approval work. Imported VERIFIED state can never skip review.

## Operation and limitations

Apply the migration with `backend/.venv/Scripts/alembic.exe -c backend/alembic.ini upgrade head` from the repository root (or `alembic upgrade head` from backend with the configured local environment). Source PDFs must remain available under configured data_root. A1 has backend APIs and uses the existing approval queue; it does not add a registry frontend. Approval validity/expiry continues to follow existing settings.

Downgrade cannot discard immutable A1 audit events: restoring the older event CHECK fails if such events exist. Retain audit history and use an explicit migration plan in that case. No administrative database/schema mutation is defended against as tamper-proof; content binding and audit checks are tamper-evident.

The Phase 10 benchmark interface, cases, validators and prior results remain frozen and untouched. No validation/blind benchmark inference is part of A1.
