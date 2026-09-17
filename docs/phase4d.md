# Phase 4D — Safety & incident agent

Replaces the 4B stubs for `safety` and `combined_safety_maintenance`.
Output schemas: **S7** (action-adjacent recommendation, phrased as a
proposal), **S5** (refusal).

Written as part of the unsupervised autonomous run described in
`docs/phase4-autonomous-continuation.md`; see `docs/phase4-decisions.md`
D-010 through D-012 for this sub-phase's non-obvious choices.

## New modules

```
app/agents/safety_language.py     deterministic authorisation-language validator (shared with 4F)
app/agents/prompts/safety.py      system prompt + user-message framing
app/agents/nodes/safety.py        the safety agent itself (handles both routes)
```

Modified (additive): `app/agents/enforcement.py` (new
`enforce_citations_and_authorization_language`, and an `EnforcementFailure`
base class that `CitationEnforcementFailure` now subclasses — no change to
`enforce_citations()`'s existing behaviour or tests), `app/agents/graph.py`
(routes `safety` and `combined_safety_maintenance` to `safety_node`),
`app/agents/prompts/knowledge.py` / new `app/agents/prompts/shared.py`
(evidence-block formatting factored out so both specialists use one
implementation — `knowledge.py` re-exports it, so every existing 4C import
still works unchanged).

## The safety property: no output ever reads as authorisation to act

Three independent layers, matching the brief's four build items:

1. **`app/agents/safety_language.py`** — a fixed list of forbidden
   constructions ("you are cleared to", "permission granted", "you may now
   isolate/proceed/...", "authorised to", "permit issued/approved", "go
   ahead and...", "cleared for isolation/entry/work") scanned over the
   model's own free-text fields (`summary`, `warnings`, each proposed
   action's `action` text). A narrow negative lookahead keeps "authorised
   to *request/obtain/seek*..." from being flagged — reporting that a
   permit must be requested is not the same claim as granting one. See
   D-010 for why this list is broader than the brief's four literal
   examples, and why it is a floor, not a ceiling.

2. **`enforce_citations_and_authorization_language()`**
   (`app/agents/enforcement.py`) — the same bounded reject-or-regenerate
   shape as 4C's `enforce_citations()`, but checking citation validity AND
   authorisation language in a single loop: one regeneration attempt fixes
   both problems if both are present, never two separate budgets stacked.
   A failure after that raises `EnforcementFailure` (the new common base
   class both this and `enforce_citations()`'s `CitationEnforcementFailure`
   share), carrying a ready S5 refusal that directs the requester to escalate
   to a qualified human — never the rejected recommendation.

3. **`_harden_action_recommendation()`** (`app/agents/nodes/safety.py`) —
   after enforcement passes, the node still overrides two fields
   deterministically, never trusting the model's own value: any
   `approval_status="approved"` is downgraded to `"required"`
   unconditionally (this system never self-approves an action), and
   `human_approval_required` is forced `True` at the top level whenever any
   proposed action's `action_class` is not `"informational"`. See D-012 for
   why this is *recording accurately*, not the approval *enforcement*
   Phase 5 owns — 4D still always returns synchronously, gates nothing, and
   builds no workflow.

## Conservative escalation

The system prompt (`app/agents/prompts/safety.py`) instructs the model
directly: when severity is ambiguous, choose the more cautious
`action_class`, treat any H2S or high-high condition as requiring immediate
human escalation, and never imply a lower severity than the evidence
supports. This is a prompt-level instruction, not a code-enforced one — S7
carries no dedicated `severity` field to enforce against (the schema, fixed
in 4C, only has `action_class`/`approval_status`/`confidence`/`warnings`),
so escalation is expressed through which `action_class` and `warnings` the
model chooses. The dominant `action_class` reported at the
`WorkbenchState["action_class"]` level is computed deterministically in
code (`_dominant_action_class`) as the single most severe class among a
turn's proposed actions (`shutdown` > `isolation` > `process_change` >
`inspection` > `informational`), so a mixed-severity response cannot
under-report its own worst action at the state/trace level even if the
model's own field ordering is inconsistent.

## `combined_safety_maintenance`

The same `safety_node` handles both routes (D-004's own design). For
`combined_safety_maintenance` specifically, `_gather_evidence()`
deterministically extracts equipment tags from the query text
(`app.services.sparse.identifiers`, the same extractor `retrieval.py`
already uses for its identifier-miss warning — no model call, see D-011),
and for up to 3 distinct tags calls the already-registered
`get_maintenance_history` and `get_latest_reading` tools, folding each
returned row into an evidence block (`json.dumps` of the row, since
structured-data evidence refs carry no `.quote` field the way document
chunks do). The plain `safety` route never touches these tools — tested
explicitly (`test_pure_safety_route_never_calls_maintenance_or_sensor_tools`).

## No authorisation implication from `access_scope`

`access_scope` does not appear anywhere in this sub-phase's evidence
gathering, prompt, or schema handling — it is Phase 3A/3B metadata used
only for retrieval filtering (`app/schemas/knowledge.py`'s
`RetrievalFilters.access_scope`), never read or surfaced by
`nodes/safety.py`. There is therefore nothing in this sub-phase that could
phrase a scope filter as clearance; this item of the brief is satisfied by
absence, not by an explicit check, and is noted here so a future reviewer
does not go looking for one.

## Limitations

- The authorisation-language list (D-010) is necessarily incomplete
  against open-ended model phrasing; treat it as one layer, not the only
  one, until Phase 5's approval gate exists.
- No dedicated `severity` field exists in S7 to enforce escalation against
  in code; escalation is currently prompt-level only (`action_class` choice
  and `warnings`), not independently code-verified the way citation
  validity and authorisation language are.
- `combined_safety_maintenance`'s tag extraction is regex-based and will
  miss an equipment reference phrased without a recognizable tag pattern
  (e.g. a bare equipment name with no `P-204`-style identifier) — in that
  case the route behaves exactly like plain `safety` (SOP/incident evidence
  only), which is a safe degradation, not a crash, but is a narrower result
  than a query naming the equipment by name alone might expect.
