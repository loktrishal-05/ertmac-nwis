# Phase 4C — Knowledge & multimodal retrieval agent

Replaces the 4B `knowledge` stub, and the `guardrail_refusal`/`clarification`
terminal stubs, with real nodes. Output schemas: **S1** (grounded answer),
**S3** (OCR-derived equipment-tag identification), **S5** (refusal — now
shared by every route that needs one, not only `knowledge`).

Written as part of the unsupervised autonomous run described in
`docs/phase4-autonomous-continuation.md`; see `docs/phase4-decisions.md`
for every non-obvious choice made while building this (D-005 through D-009).

## New modules

```
app/schemas/agent_outputs.py     S1-S7 Pydantic contracts, shared 4C-4F (unit 1)
app/agents/enforcement.py        refuse() + enforce_citations() (unit 1-2)
app/agents/prompts/knowledge.py  system prompt + evidence-block framing (unit 3)
app/agents/nodes/knowledge.py    the knowledge agent itself (unit 4)
app/agents/nodes/terminal.py     guardrail_refusal_node, clarification_node (unit 1/5)
```

Modified (additive): `app/agents/graph.py`, `app/api/routes/query.py`,
`app/core/config.py`, `backend/scripts/smoke_agents.py`.

## `app/schemas/agent_outputs.py` — S1 through S7, defined once

All seven output schemas are defined in one module rather than one per
sub-phase, derived only from `docs/model-evaluation-spec.md` lines 91-121
("## 4. Expected output schemas") — never from that file's case table
further down (see D-002). Every model uses `extra="forbid"`. Two schema-level
enforcements worth calling out because 4E/4F inherit them directly:

- `MaintenanceHypothesis` (used by S4 and S6) has a `model_validator` that
  **structurally rejects** a hypothesis carrying neither
  `supporting_evidence` nor `contradicting_evidence` — this is 4E's own
  requirement, built now because the schema is shared.
- `EquipmentTag.status` is a closed three-value enum
  (`verified`/`ambiguous`/`unverified`); the schema itself cannot know
  *when* `verified` is legitimate to emit (that needs a registry lookup at
  runtime), so that enforcement lives in `nodes/knowledge.py`, tested in
  `tests/test_agents_knowledge.py`, not in the schema.

## `app/agents/enforcement.py` — refuse() never calls the model

Every S5 `Refusal` in 4C-4F is built by `refuse()`, a pure Python function
that never touches the model gateway. A refusal's reason, missing evidence,
and safe next step are already known to the calling code — from a tool
result, a validator's error, or the router's own classification — so asking
the model to *phrase* the refusal risks it inventing a plausible-sounding
but false justification for a security-relevant outcome. This is D-006;
`guardrail_refusal_node` and `clarification_node` (below) are built on the
same helper, closing the D-004 gap where those two terminal routes had no
schema-valid output at all.

`enforce_citations()` is the reject-or-regenerate control flow the 4B
citation validator (`app.agents.citations.validate_citations`) was built for
but did not itself implement: it calls a `generate(retry_note)` callback, and
on an invalid citation set, calls it exactly once more with the validator's
own unknown-id list folded into a retry note, then raises
`CitationEnforcementFailure` carrying a ready S5 body. **The bad citation is
never stripped and shipped** — a caller that caught this exception and
returned the prior (invalid) answer anyway would defeat the entire point;
`nodes/knowledge.py` does not do that, and a test
(`test_persistently_invalid_citation_refuses_and_never_ships_the_answer`)
would fail if it did.

## `app/agents/nodes/knowledge.py` — the agent

One tool call, `retrieve_documents`, gathers all evidence for a turn
(`get_pid_regions` is a 4B-registered tool but is not called by this node —
see Limitations). The node then does exactly one of three things,
deterministically:

1. **Insufficient evidence → S5.** `_assess_evidence()` is a pure Python
   function, not a prompt instruction, combining two independent signals:
   the retriever's own identifier-miss warning (`"No lexical evidence
   matched..."`, from `app/services/retrieval.py`) and a configurable
   relevance floor (`KNOWLEDGE_RELEVANCE_FLOOR`, default `0.0`) applied to
   the top result's score. **Either signal alone refuses** — an identifier
   miss refuses regardless of what any neighbour scored, because Phase 3B2
   (`docs/phase3b2-validation.md`) measured dense/hybrid retrieval returning
   unrelated neighbours, sometimes at an unremarkable score, for a
   nonexistent identifier (`ZZQ-99999`); trusting the score alone in that
   situation would silently answer from a neighbour. This is the more
   conservative of the two readings of the 4C brief's wording and is logged
   as D-007. No model call happens on this path.

2. **OCR-derived evidence present → S3.** If any gathered evidence is an
   OCR-derived `document_chunk` (i.e. it came from a P&ID whose text was
   chunked in Phase 3B1/3B2), the node builds `EquipmentTag` entries
   directly from that evidence — no model call. `status` is computed
   entirely in code: a registry lookup (`Equipment` table, exact match on
   `normalize_equipment_tag(quote)`) confirms `verified`; otherwise the
   OCR pipeline's own `unverified`/`ambiguous` status is carried through.
   **OCR confidence never enters this decision, however high** — a test
   fixes `ocr_confidence=0.99` with no registry match and asserts the
   status still is not `verified`.

3. **Otherwise → S1**, via `generate_structured` against `GroundedAnswer`.
   Retrieved chunk text is framed as explicitly delimited, labelled
   `<evidence id="..." locator="...">` blocks in the user message; the
   system prompt (`app/agents/prompts/knowledge.py`) states plainly that
   these blocks are quoted data, not instructions, and that an
   instruction-shaped block must not be obeyed. `enforce_citations()` wraps
   the generation call; a `StructuredOutputError` from the gateway (schema
   violation after 4A/4B's own repair budget is exhausted) is treated the
   same as an unfixable citation failure — refuse, don't propagate.

## `nodes/terminal.py` — guardrail_refusal and clarification

Per D-004, these two routes are terminal and non-agentic: no specialist
agent runs for them. They now emit a schema-valid S5 built from the
router's own `route_reasoning`, closing the gap where 4B left them on the
generic `not_implemented` stub.

## Graph and session wiring (D-008)

`build_graph()` gained an optional `session=None` parameter. 4B's cached
`get_graph()` singleton works because its only stateful dependency (the
model gateway) is itself a process-wide singleton; a SQLAlchemy `Session` is
request-scoped and cannot be baked into a cached graph the same way. Rather
than restructure the 4B caching pattern, `run_graph()` now takes an optional
`session` keyword: `session=None` (the default, used by every existing 4B
test) keeps using the cached `get_graph()` exactly as before; a real
`session` (now passed by `POST /query`) builds a fresh graph for that
request, with `knowledge_node` bound to it by closure — the same pattern
4B's own `router_node` already uses for the gateway. `_traced()` and every
4B node signature are untouched.

## `KNOWLEDGE_RELEVANCE_FLOOR` — provisional, HIGH review (D-006 refers to
refuse(); the floor default itself is discussed in `nodes/knowledge.py`'s
module docstring and D-007; the number itself is D-009)

`docs/phase3b2-validation.md` states outright: "There is no calibrated
rejection threshold." `RetrievedChunk.score` is, under the default
`hybrid_rerank` strategy, a raw cross-encoder logit
(`app/services/reranking.py`: "scores are raw logits, never
probabilities") — unbounded, not a 0-1 relevance probability. `0.0` was
chosen as a defensible, conservative default (a cross-encoder logit at or
above zero is, per the reranker's own training objective, a non-negative
relevance signal), but it is **not** a calibrated number and the operator
should tune `KNOWLEDGE_RELEVANCE_FLOOR` against real traffic once available.

## Limitations

- `get_pid_regions` is registered as a tool (4B) but is not invoked by this
  node. S3 emission is scoped to OCR-derived `document_chunk` evidence that
  `retrieve_documents` already returns (Phase 3B1/3B2 chunk PID OCR text
  into the same index as SOPs); a query that names a specific P&ID drawing
  by `document_version_id` and expects a full region-by-region tag sweep
  would need a second tool call this node does not make. Flagged here
  rather than silently guessed at; a natural 4C+ follow-up, not required by
  the continuation brief's stated smoke items.
- `equipment_type` and `normalized_tag` on an S3 `EquipmentTag` are computed
  by simple normalization (`normalize_equipment_tag`), not inferred by the
  model — the model is not consulted at all on the S3 path. This is more
  conservative than the brief strictly requires (which only pins `status`),
  and means `equipment_type` is always `None` today.
- No multi-turn conversation, no streaming, no checkpointer — unchanged
  from 4B's scope, not part of 4C's brief either.
