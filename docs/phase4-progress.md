# Phase 4 autonomous run — progress

Last updated: 2026-09-17T00:00:00Z (updated at each boundary)
Current sub-phase: 4E
Current unit: 1 of N — not started

## Status
| Sub-phase | Status | Tests | Self-audit | Commit | Notes |
|---|---|---|---|---|---|
| 4A | COMPLETE | (pre-existing) | — | (pre-existing, prior session) | Model gateway; see docs/phase4a.md |
| 4B | COMPLETE | 169 | PASS | (this session) | Retroactive report; see docs/phase4b.md, docs/phase4b-validation.md |
| 4C | COMPLETE | 210 (+41) | PASS | (this session) | Knowledge agent; see docs/phase4c.md, docs/phase4c-validation.md |
| 4D | COMPLETE | 235 (+25) | PASS | (this session) | Safety & incident agent; see docs/phase4d.md, docs/phase4d-validation.md |
| 4E | NOT_STARTED | | | | |
| 4F | NOT_STARTED | | | | |

## Resume instructions for a fresh session

1. Read this file and `docs/phase4-decisions.md` fully before acting.
2. Do not restart 4B, 4C, or 4D — all three are complete, tested (235 tests
   total), documented (`docs/phase4b*.md`, `docs/phase4c*.md`,
   `docs/phase4d*.md`), and their self-audit gates passed.
3. If `Current sub-phase` above is `IN_PROGRESS`, resume from `Current unit`
   — do not re-derive decisions already logged in `docs/phase4-decisions.md`.
4. Route-to-sub-phase mapping (D-004), all now built except 4E/4F:
   knowledge->4C (done), safety->4D (done), combined_safety_maintenance->4D
   (done, reusing already-registered maintenance/sensor tools — see D-011),
   maintenance->4E (next), process_optimization->4F,
   guardrail_refusal/clarification->`app/agents/nodes/terminal.py` (done in 4C).
5. S1-S7 schema field lists are pinned in `app/schemas/agent_outputs.py`
   (all seven defined already, in 4C) — do not re-read
   `docs/model-evaluation-spec.md`; the shapes are already available by
   import. `MaintenanceHypothesis`'s structural evidence-array requirement
   (needed by 4E's S4/S6) is already built and tested
   (`tests/test_agent_outputs.py::MaintenanceHypothesisEvidenceTests`).
6. The evaluation-asset hash guard is
   `backend/tests/test_evaluation_asset_guard.py` (D-003) — must pass,
   unchanged, at the end of every sub-phase. Still pinned to
   sha256=beb507819082539dcdbf3c5b1ff1e30a5590cd071258af6ca8ec475d7f23e0b4;
   unchanged through 4D.
7. Shared infrastructure now available to 4E/4F, built during 4C/4D:
   - `refuse()` / `enforce_citations()` / `enforce_citations_and_authorization_language()`
     / `EnforcementFailure` (base) / `CitationEnforcementFailure` (subclass)
     in `app/agents/enforcement.py`.
   - `app/agents/safety_language.py`'s `find_authorization_language()` —
     4F's brief explicitly says to reuse this, not reimplement it.
   - `app/agents/prompts/shared.py::format_evidence_block()` — reused by
     `prompts/knowledge.py` and `prompts/safety.py`; 4E/4F should use it too
     rather than defining a third copy.
   - `build_graph(session=...)` / `run_graph(query, session=...)` session
     threading (D-008) — a session-needing node is added to `graph.py`'s
     `route_nodes` dict the same way `knowledge_node`/`safety_node` are.
   - `app.services.sparse.identifiers()` for deterministic equipment-tag
     extraction from free text (D-011) — reuse this in 4E rather than
     re-deriving a tag-extraction regex.
8. Local commits are permitted and expected at each sub-phase boundary
   (message form `phase4d: <summary>`, etc.). Never push.
9. 4E builds the maintenance & asset reliability agent (S4, S6) per
   `docs/phase4-autonomous-continuation.md` section 7. The centerpiece is
   the threshold loop: the model locates a numeric limit in cited SOP text;
   Python (not the model) extracts that numeral and passes it into
   `compute_sensor_features(thresholds.maximum=<value>)`
   (`app/agents/tools/sensors.py`, already built in 4B — it deliberately
   accepts a caller-supplied threshold and invents no default); the
   comparison itself already happens inside Phase 3C's own code path via
   that tool. A threshold with no SOP citation must be rejected — this is a
   new validator this sub-phase must write, there is nothing to reuse for
   it. The asymmetric observation/hypothesis wording ban ("bearing",
   "failure", "damage", "cavitation", "diagnos", "impeller" forbidden in
   `observations[]`, permitted in `hypotheses[]`) is also new; Phase 3C's
   existing `test_no_observation_ever_names_a_diagnosis` is the flat-ban
   precedent to generalize, not to duplicate.

## Open provisional decisions

- D-002 (HIGH): benchmark-file grep contamination while locating S1-S7
  shapes — no case content retained or used; operator should independently
  verify per the entry's "Reversible" note.
- D-003 (HIGH): evaluation-asset hash guard created from scratch (none
  existed) — operator should confirm this is an acceptable enforcement
  mechanism, or replace it with their own if one exists elsewhere.
- D-004 (HIGH): route-to-sub-phase mapping, including the
  `combined_safety_maintenance` -> 4D choice — operator should confirm this
  matches their intended product design.
- D-007 (HIGH): the knowledge agent's identifier-miss check refuses
  regardless of the top-scoring neighbour's score, not only when the score
  is also low — this changes how often the knowledge agent refuses on real
  traffic; operator should confirm this matches their tolerance.
- D-009 (HIGH): `KNOWLEDGE_RELEVANCE_FLOOR` defaults to `0.0`, an
  uncalibrated number (Phase 3B2 explicitly found none to inherit) —
  operator should tune against real retrieval traffic before production use.
- D-010 (HIGH): the authorisation-language validator's pattern list is
  necessarily incomplete against open-ended model phrasing — operator
  should red-team it with paraphrases before treating it as a sole
  safeguard; Phase 5's approval gate is the real control.
- D-012 (HIGH): `nodes/safety.py` overrides the model's own
  `approval_status`/`human_approval_required` values deterministically —
  operator should re-confirm this framing (recording vs. enforcing) before
  Phase 5 is built on top of these fields.
