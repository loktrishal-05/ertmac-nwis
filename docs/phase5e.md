# Phase 5E — deterministic pre-routing guardrails

Phase 5A, 5B, 5C, and 5D are accepted and committed. This change implements
only 5E: a deterministic, pre-routing safety/domain gate that runs BEFORE the
LangGraph router, in plain Python, with no model call. It does not implement
5F or the Verified Knowledge Cache/adaptive FAQ caching/voice/multilingual/BI
work explicitly deferred by the task brief.

**The LLM never decides this boundary.** Exactly the same posture Phase
5A/5B/5C/5D already hold for governance/approval/audit/evidence integrity:
`app.services.preflight.run_preflight` is deterministic backend code, called
once per `/query` request, before `run_graph`.

## Implemented

- A single deterministic gate (`app.services.preflight.run_preflight`)
  combining four independent checks, each able to end the request before any
  gateway call: access-scope validity, prompt-injection detection, unsafe
  plant-action detection, and company-domain classification.
- Company-domain classification into `IN_SCOPE` / `OUT_OF_SCOPE` /
  `UNCERTAIN`, composed from the existing Phase 3B1 tag vocabulary
  (`app.services.tags`), a bounded known-intent phrase list, and a bounded
  out-of-domain marker list — never naive single-keyword matching.
- A deterministic, bounded `OUT_OF_SCOPE` refusal and a deterministic
  `UNCERTAIN` clarification request, both built from the existing S5
  `Refusal` schema (`app.agents.enforcement.refuse`) — the identical shape
  the graph's own `guardrail_refusal`/`clarification` terminal nodes already
  produce, not a second response format.
- A prompt-injection preflight reusing `app.agents.safety_language`'s
  quote-stripping technique (now extracted as `strip_quoted_spans`) so a
  quoted example of an injection phrase inside legitimate company content
  (an incident report, say) is never itself treated as an attempt.
- An unsafe plant-action preflight that distinguishes a request asking the
  AI to PERFORM/AUTHORIZE a plant action ("Start P-204") from an
  INFORMATIONAL question about one ("What SOP describes shutdown of
  P-204?"), and refuses the former outright rather than mis-routing it as a
  normal informational query.
- Access-scope enforcement: the request's `access_scope` must be one of a
  small, deterministic, hand-maintained whitelist
  (`app.services.preflight.SUPPORTED_ACCESS_SCOPES`); anything else fails
  closed.
- Zero-model-call behaviour: a `REFUSE`/`CLARIFY` preflight decision returns
  directly from `POST /query`, never calling `run_graph` (and therefore never
  the router, never the model gateway).
- Phase 5C audit integration: five new, bounded audit event types
  (`PREFLIGHT_OUT_OF_SCOPE_REFUSED`, `PREFLIGHT_INJECTION_REFUSED`,
  `PREFLIGHT_UNSAFE_ACTION_REFUSED`, `PREFLIGHT_SCOPE_DENIED`,
  `PREFLIGHT_CLARIFICATION_REQUIRED`), appended best-effort (nothing
  authoritative changed, so a logging failure must never turn a correct
  refusal/clarification response into a 500) via the existing
  `app.services.audit.append_event` — no second audit system. An `ALLOW`
  decision is never audited, so the chain is not flooded by harmless queries.

## Not implemented

- Phase 5F final governance/security acceptance.
- The Verified Knowledge Cache / semantic FAQ cache, adaptive answer
  caching, voice assistant, multilingual support, or BI dashboard — all
  explicitly out of scope for this phase.
- Any plant-control write path, SCADA/DCS integration, or new tool beyond
  the existing seven read-only tools (verified unchanged by
  `test_no_scada_dcs_tool_exists`).
- A per-role access-scope hierarchy mapping authenticated users to a maximum
  permitted `access_scope`. `access_scope` remains, as documented since
  Phase 3A/4D, metadata/filtering only, never itself an authorization claim
  about the caller's identity; Phase 5E's contribution is a deterministic
  whitelist check on the value itself (fail closed on anything unsupported),
  not a new authentication/authorization system. Building a real per-role
  scope ceiling is future work, not invented here.
- A frontend preflight-status UI (out of scope; no `frontend/src/App.jsx`
  change was made or needed).

## Architecture: where preflight sits

```
request
  |
  v
replay_request (Phase 5A idempotency: an already-governed request_id
                keeps replaying its original committed draft, unchanged)
  |
  v
run_preflight(query, access_scope)          <-- NEW, Phase 5E
  |
  +-- REFUSE  -> deterministic S5 refusal, best-effort audit, NO model call
  +-- CLARIFY -> deterministic S5 clarification, best-effort audit, NO model call
  +-- ALLOW   -> run_graph (LangGraph router -> specialists)
                   |
                   v
                Phase 5A-5D governance/approval/audit/evidence boundary
                (unchanged)
```

`app/api/routes/query.py`'s `query()` handler is the only integration point.
`replay_request` runs first (unchanged Phase 5A contract: a retried
`request_id` must not be reclassified by a since-changed preflight rule);
`run_preflight` runs second, strictly before `run_graph`.

## Company-domain classification design

`app.services.preflight.classify_domain(query)` composes multiple
independent signals rather than a single keyword list:

- **Strong signals** (-> `IN_SCOPE`): an equipment/instrument/line-number tag
  hit (`app.services.tags.extract_tags`, reused unchanged from Phase 3B1), a
  `SOP-<number>` reference, a known equipment-type noun (pump, valve,
  compressor, motor, tank, vessel, ...), or a bounded known-intent phrase
  ("maintenance history", "incident report", "pending approvals", "work
  order", "vibration trend", ...).
- **Out-of-domain markers** (-> `OUT_OF_SCOPE`, only when no strong signal is
  also present): a bounded, deliberately non-exhaustive list of clearly
  non-industrial topics (entertainment, sports, cryptocurrency, weather,
  horoscopes, dating advice, general trivia). Composing this with the
  strong-signal check means a company/brand-shaped token sitting next to an
  unrelated request cannot bypass the gate
  (`test_company_name_does_not_bypass_domain_gate`).
- **Weak/generic industrial nouns** (-> `UNCERTAIN` when nothing else
  matched): physical-quantity/property words (pressure, temperature, flow,
  level, ...) that are real industrial vocabulary but carry no
  equipment/procedure/tag context -- exactly the brief's own "Tell me about
  pressure" example.
- **No signal at all** (-> `UNCERTAIN`): the conservative default is to ask,
  never to guess in either direction.

This list is bounded and admittedly non-exhaustive, in the same spirit as
D-010's own documented incompleteness (`docs/phase4-decisions.md` D-010) --
extending it is a plain code change, not a data-driven system, matching how
`app.services.tags.DEFAULT_PATTERNS` and `app.agents.safety_language._PATTERNS`
are already maintained.

## Out-of-scope behaviour

A deterministic, bounded refusal: *"This workbench is restricted to
authorized organizational and industrial tasks."* Built via the same
`app.agents.enforcement.refuse()` helper the graph's own
`guardrail_refusal_node` already uses (`status="refused"`), returned as a
normal `200` response with `agent_result.output.status == "refused"`,
`route: null` (no routing ever happened), `governance_status:
"INFORMATIONAL"`. No governance revision, no `AgentRun`, no model call.

## Clarification behaviour

`UNCERTAIN` domain classification returns `status="clarification_required"`
(the identical shape the graph's own `clarification_node` produces), naming
the missing evidence ("equipment tag, SOP/document reference, or other
company context") rather than fabricating plant context. No model call.

## Injection handling

`app.services.preflight._detect_injection` scans the query (with quoted
spans stripped via `app.agents.safety_language.strip_quoted_spans`) against
a bounded, case-insensitive pattern list covering: "ignore ... instructions",
"disregard/forget ... instructions/rules/policy", "reveal/show the system
prompt", "bypass approval", "pretend I am/you are admin", "act as admin",
"disable safety checks", "you are now in developer/admin/unrestricted mode".
A match REFUSEs before any model call. Retrieved documents are never
re-scanned by this gate at all -- `run_preflight` only ever receives the raw
user `query` string, never evidence/tool-result text -- so a retrieved
document's own content can never be treated as an authorization instruction
by construction, not by a runtime check
(`test_retrieved_evidence_is_never_given_a_system_role` additionally
confirms every specialist node embeds gathered evidence as `role="user"`
content, never `role="system"`, matching `docs/phase4d.md`'s identical "by
absence" precedent for `access_scope`). D-010 (`app.agents.safety_language`)
is unchanged and continues to apply only to specialist OUTPUT -- it is never
consulted by this gate and never authorizes anything.

## Unsafe-action handling

`app.services.preflight._detect_unsafe_action` splits the (quote-stripped)
query into sentences; a sentence containing an informational marker ("what",
"describe", "explain", "SOP", "procedure for", "how do I", ...) is skipped,
never flagged. A remaining sentence matching an imperative action-verb
pattern (start/stop/open/close/isolate/bypass/override/..., optionally
directed at an equipment tag), an "issue/complete a permit/LOTO" request, a
"claim isolation" statement, or an "operate/control SCADA/DCS" request
REFUSEs before any model call, with a reason explicitly stating the
workbench has no plant-control capability. An informational question about
the same procedure ("What SOP describes shutdown of P-204?") is unaffected
and reaches the graph normally. The tool registry remains exactly the seven
existing read-only tools -- no SCADA/DCS tool exists to route to in the
first place (`test_no_scada_dcs_tool_exists`).

## Access-scope enforcement

`app.services.preflight.SUPPORTED_ACCESS_SCOPES` is a small, explicit,
hand-maintained whitelist (`{"internal"}` today -- the only value this
deployment's retrieval layer actually ingests/serves, per
`docs/phase3a.md`). A request whose `access_scope` is not in that set is
REFUSEd, fail-closed, before any model call. Reuses Phase 5B's existing
authentication (`app.api.deps.get_optional_current_user`) unchanged -- no
new auth mechanism is introduced. `access_scope` itself continues to come
only from the validated `QueryRequest` schema (`extra="forbid"`, so a client
cannot smuggle in an authority-shaped field alongside it) and is never
written anywhere except once, in `run_graph`, from that same request value
(`app.agents.context.set_access_scope`) -- no node, prompt, or tool ever
calls it, so a model can never widen or change the scope a request was made
under (`test_model_output_cannot_change_access_scope` confirms this by
source inspection).

## Zero-model-call behaviour

`REFUSE`/`CLARIFY` return directly from the `/query` handler; `run_graph` --
and therefore the LangGraph router and the model gateway -- is never called.
Proven both by unit test (`app.api.routes.query.run_graph` mocked and
asserted `not_called()`) and live, against real Ollama/Qdrant/PostgreSQL: an
out-of-scope/injection/unsafe-action/ambiguous request returns in under
0.25s, versus ~90s for a legitimate query that genuinely reaches the router
and a specialist (see `docs/phase5e-validation.md`).

## LangGraph integration

Unchanged beyond the new preflight call in `query.py`: `run_graph`, the
router, every specialist node, and the Phase 5A-5D governance/approval/audit/
evidence boundary are untouched. `ALLOW` is the only decision that reaches
`run_graph`; everything downstream of that call behaves exactly as before.

## Audit integration

Reuses the existing Phase 5C chain exclusively (`app.services.audit.
append_event`) -- no second audit system, no new table. Migration
`0009_phase5e_preflight` (follows `0008_phase5d_evidence_integrity`) widens
only the `audit_events.event_type` CHECK constraint to admit the five new
event types; no new table is created, since the preflight gate has no
persisted domain object of its own. Every preflight denial/clarification
event is best-effort (matching the exact split Phase 5C already established
for `APPROVAL_AUTHORIZATION_DENIED`/`ADVISORY_RELEASE_DENIED`): nothing
authoritative changed, so an audit-append failure must never turn an
already-correct `200` refusal/clarification response into a `500`. Payloads
carry only `decision`, `domain_status`, `reason_code`, `detected_risks`
(category labels, never raw matched text), `access_scope`, and
`query_length` -- never the raw query text or any secret. `ALLOW` is never
audited by this gate, so the chain is not flooded by harmless queries.

## Reuse, not duplication

- `app.services.tags.extract_tags`/`DEFAULT_PATTERNS` (Phase 3B1) -- reused
  unchanged for tag detection.
- `app.agents.safety_language.strip_quoted_spans` -- extracted from the
  existing D-010 quote-stripping logic and reused by both modules; D-010's
  own behaviour (`find_authorization_language`/
  `contains_authorization_language`) is otherwise untouched.
- `app.agents.enforcement.refuse()` and the S5 `Refusal` schema
  (`app.schemas.agent_outputs.Refusal`) -- reused so a preflight refusal is
  byte-shape-identical to the graph's own `guardrail_refusal`/
  `clarification` terminal-node output, not a second response format.
- `app.services.audit.append_event` (Phase 5C) -- reused for every preflight
  event; no second audit system.
- `app.api.deps.get_optional_current_user` (Phase 5B) -- reused unchanged
  for the actor identity attached to a best-effort audit event; no new
  authentication mechanism.

## D-010 (unchanged)

`app.agents.safety_language` continues to apply only to SPECIALIST OUTPUT
(the model's own generated text), as it has since Phase 4D. Phase 5E does
not call it, does not change its pattern list, and does not let it authorize
anything -- it remains a supplemental heuristic signal only, never this
phase's (or any phase's) authorization boundary.
