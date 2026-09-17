# Phase 4F — Process optimization agent

Replaces the 4B stub for `process_optimization`. Output schemas: **S6, S7**.

Written as part of the unsupervised autonomous run described in
`docs/phase4-autonomous-continuation.md`; implements the requirements in
section 8.

## New modules

```
app/agents/prompts/optimization.py    system and user message construction
app/agents/nodes/optimization.py      the process optimization agent (both schemas)
```

Modified (additive): `app/agents/graph.py` (routes `process_optimization`
to `optimization_node`).

## The safety property: every set-point or valve suggestion is a proposal for human review, never an instruction

Two independent implementations:

### 1. Authorisation-language validator (reused from 4D)

The agent's summary, warnings, and proposed actions are scanned by the same
`enforce_citations_and_authorization_language()` function (from
`app.agents.enforcement`) that 4D uses. If the output contains forbidden
phrasings like "you are cleared to", "permission granted", "you are
authorized to", etc., the model is given one bounded regeneration attempt,
then the output is refused as S5. The validator is deterministic: a regex
pattern match over the output text.

### 2. Deterministic hardening of action recommendations

`_harden_process_change_recommendation()` (modelled on 4D's
`_harden_action_recommendation`) forces every proposed action's
`action_class` to "process_change" and `approval_status` to "required",
regardless of what the model proposed. The top-level
`human_approval_required` is forced to true. This runs *after* the model
generates the proposal and before the agent emits S7, ensuring no action
escapes the node without being re-tagged as requiring human approval.

## Confounder acknowledgement

Phase 4F's brief explicitly requires the agent to surface competing
explanations for correlated trends rather than asserting causation from
correlation. This property is **prompt-enforced, not code-enforced** — there
is no way to deterministically verify whether the model considered a
confounder the way citation validity or authorisation language can be
checked. The implementation is in `OPTIMIZATION_SYSTEM_PROMPT` and validated
by a fixture test:

- `test_confounder_fixture_validates_multiple_trends_acknowledged` passes
  evidence where two variables (e.g. differential pressure and flow) both
  rise in the same window
- The test asserts that the response mentions both trends and acknowledges
  their co-movement
- If the response names only one trend or hides competing explanations, the
  test fails

## Evidence gathering

The agent collects:

1. **Documentation (SOPs, operational references)** via `retrieve_documents`,
   providing context and baseline parameters
2. **Latest sensor reading** via `get_latest_reading`, to identify the
   sensor_tag for trend analysis
3. **Sensor trends** via `compute_sensor_features` (no thresholds), which
   returns pre-computed slope, percentage_change, and other metrics from
   Phase 3C — the model never computes these
4. **Maintenance history** via `get_maintenance_history`, for operational
   context

All sensor arithmetic is deterministic Python (Phase 3C's
`compute_sensor_features`); the model proposes and phrases improvements
only.

## Equipment tag requirement

Like maintenance (4E), the optimization domain is asset-scoped: the query must
name an equipment tag, extracted deterministically via
`app.services.sparse.identifiers()`. If no tag is found, the node refuses
with `status="insufficient_evidence"`.

## Test coverage

9 tests in `tests/test_agents_optimization.py`:

- **Hardening tests** (4): action_class forced to process_change,
  approval_status forced to required, human_approval_required forced to
  true, multiple actions all hardened
- **Node behaviour** (5): no equipment tag refused, no evidence refused,
  valid proposal hardened before emitting, authorisation language triggers
  one regeneration, confounder fixture validates both trends acknowledged

All 82 agent tests (4C+4D+4E+4F) pass.
