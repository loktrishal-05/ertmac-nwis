# Advanced-A2: adaptive local execution

Advanced-A2 adds a conservative execution selector above the existing A1 registry, hybrid retrieval and LangGraph. It does not change benchmark assets, model templates or plant-control authority.

## Execution hierarchy

`/query` retains authentication, replay conflict handling and current deterministic preflight before serving any answer. An authenticated exact A1 verified hit wins first. After a miss, the adaptive service applies deterministic rules, checks bounded approved packs and optionally asks a local strategy planner. Every resulting state still passes through `govern_response`; approval releases an advisory only.

| Path | Eligibility and implementation |
| --- | --- |
| VERIFIED_FAST_PATH | Existing A1 exact static-fact match, current source bindings, scope and human approval. |
| CAG_PATH | One exact approved pack, valid members/sources/approval, internal authenticated scope. Returns the reviewed aggregate with existing citations. |
| HYBRID_RAG_PATH | Narrow documented-fact/document lookup grammar, or eligible planner decision. Calls the existing knowledge node through `run_graph(knowledge_only=True)`. |
| EXISTING_AGENTIC_PATH | Safety, P&ID, sensor, maintenance, operational, multi-document/deep reasoning, unknown requests and planner failures. Original LangGraph flow. |

Unknown language defaults to the existing agentic path. The optional planner is reached only for a narrow ambiguous documentation-query grammar. False negatives are intentional. The Hybrid RAG graph preserves the existing tool/access/deadline/tracing context and Phase 3B retrieval/reranking/citation pipeline and settings; no second retrieval implementation was added. A Hybrid runtime failure falls back to the full graph. An evidence-insufficiency refusal remains a refusal; it is not retried to manufacture evidence. Specialist needs are routed to the full graph before retrieval.

## System-1 authority and configuration

Strict output contains `path`, compact `reason_code`, `requires_deep_reasoning` and `requires_multiple_documents`. Only Hybrid RAG and Existing Agentic are accepted paths. Unknown fields, duplicate keys, malformed JSON or unavailable runtime fall back to Existing Agentic. Deep/multiple-document flags and non-document reason codes force Agentic. The planner cannot select trusted paths, set scope, answer, approve or control equipment. No chain-of-thought is requested or recorded.

- `SYSTEM1_ENABLED=false` by default.
- `SYSTEM1_MODEL=qwen3.5:4b` by default. Operators may select an already installed local model, including the configured primary model; an empty setting uses the primary model.
- `SYSTEM1_TIMEOUT_SECONDS=15` (maximum 120). Inventory and generation use bounded timeouts; no retry/JSON repair loop, temperature zero, 128 output tokens, thinking disabled.

The existing local model gateway and endpoint restrictions remain authoritative. Inventory is checked first. No model is pulled. Absence of the optional model does not prevent ordinary routing or the original agentic path.

## CAG packs and database

CAG here means **bounded approved context packs**, not demonstrated runtime KV-cache acceleration. This implementation deterministically composes already verified statements; it does not add another synthesis-model call.

Migration `0012_knowledge_packs` adds `knowledge_packs`: identity/creation timestamp, name, description, exact normalized question hash, member snapshot JSON and a unique foreign key to an A1 registry aggregate. The linked A1 record supplies statement, evidence, source revisions/hashes, internal scope, lifecycle, verification timestamps/reviewer, content hash and version. PostgreSQL and Qdrant remain unchanged as infrastructure.

Creation accepts 1–5 distinct VERIFIED A1 members. Limits are 10 unique source chunks, 6,000 statement characters, 16,000 characters for serialized evidence plus statements, and 2,000 characters for review metadata. Static informational eligibility is checked again. Arbitrary retrieved documents cannot become packs.

The aggregate starts CANDIDATE. Its immutable approval proposal binds pack identity, question, description and member revision/hash snapshots. An independent authorized reviewer/admin verifies it through the existing approval ledger. The aggregate question uses a review namespace, preventing it from silently masquerading as an A1 exact-question fast-path hit. No separate approval ledger is created.

Packs are immutable after creation. `pack_version` is the linked registry revision (currently 1 for each new pack). To replace a pack, revoke the old pack and create/review a new identity; simultaneous matching active packs cause conservative fallback. In-place pack editing/version increments are not implemented.

## Invalidation and governance

Inspection and lookup revalidate aggregate approval and sources, member VERIFIED state, scope, revisions and hashes, plus the immutable pack binding. Missing or out-of-scope members invalidate the pack. Source revocation, file/hash/revision changes or member staleness/revocation prevent serving. Deterministic invalidation marks the aggregate STALE and appends the existing tamper-evident lifecycle event. REVOKED and STALE packs cannot serve. Member and aggregate approval rows are locked through the serving transaction.

Invalidation runs on access, not through a background watcher. A source/runtime outage fails closed for trust and permits the existing path to continue. PostgreSQL, Qdrant and local files are not one distributed transaction; this retains the A1 limitation. Only internal scope is supported for trusted packs. Existing RBAC remains authoritative and no client/model trust flag is accepted.

Pack verification/revocation/staleness and serving reuse A1 audit events and the Phase 5 approval ledger. Serving still enters common response governance. There are no plant-write tools or execution endpoints.

## APIs

- `POST /knowledge-packs`: authenticated candidate creation; body `name`, `description`, `question`, `knowledge_ids`.
- `GET /knowledge-packs`: authenticated listing, up to 100 packs, with current lifecycle checks.
- `GET /knowledge-packs/{pack_id}`: authenticated inspection.
- `POST /knowledge-packs/{pack_id}/{verify|stale|revoke}`: reviewer/admin; existing `expected_content_hash` and `comment` review contract.
- `POST /execution/inspect`: authenticated pure deterministic preview after hypothetical verified/pack misses. Does not invoke a model, serve evidence or approve anything.

Responses expose evidence/source identities, hashes/revisions and human approval metadata. Apply migration with the existing backend `alembic upgrade head` deployment procedure before using the new pack endpoints.

## Observability and limitations

Query metadata/logs contain selected path, deterministic/system1/fallback source, reason code, fallback reason, selected planner model and planner-call count; pack identity/version or existing knowledge identity; retrieval-path label and elapsed milliseconds. `model_call_count=0` for trusted deterministic serving; complete graph call counts are unknown (`null`), not invented. Latency includes lookup and selected execution. Informational responses expose metadata through existing `knowledge_lookup`. Governed draft/replay payloads stay unchanged; execution metadata is logged separately.

No frontend work, MGS, external services, model download, benchmark tuning or validation/blind evaluation is included. Live model behavior was not required for the deterministic tests; planner failure/response tests use controlled gateway doubles.
