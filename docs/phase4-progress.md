# Phase 4 autonomous run — progress

Last updated: 2026-09-17T00:00:00Z (updated at each boundary)
Current sub-phase: 4F
Current unit: 1 of N — not started

## Status
| Sub-phase | Status | Tests | Self-audit | Commit | Notes |
|---|---|---|---|---|---|
| 4A | COMPLETE | (pre-existing) | — | (pre-existing, prior session) | Model gateway; see docs/phase4a.md |
| 4B | COMPLETE | 169 | PASS | (this session) | Retroactive report; see docs/phase4b.md, docs/phase4b-validation.md |
| 4C | COMPLETE | 210 (+41) | PASS | (this session) | Knowledge agent; see docs/phase4c.md, docs/phase4c-validation.md |
| 4D | COMPLETE | 235 (+25) | PASS | (this session) | Safety & incident agent; see docs/phase4d.md, docs/phase4d-validation.md |
| 4E | COMPLETE | 258 (+23), 1 INCONCLUSIVE (live-model timeout, D-015) | PASS | (this session) | Maintenance agent; see docs/phase4e.md, docs/phase4e-validation.md |
| 4F | NOT_STARTED | | | | |

## Resume instructions for a fresh session

1. Read this file and `docs/phase4-decisions.md` fully before acting.
2. Do not restart 4B, 4C, 4D, or 4E — all four are complete, tested (258
   tests total; 1 pre-existing live-only test is INCONCLUSIVE for a
   documented environment reason, D-015, not a code defect), documented,
   and their self-audit gates passed.
3. If `Current sub-phase` above is `IN_PROGRESS`, resume from `Current unit`
   — do not re-derive decisions already logged in `docs/phase4-decisions.md`.
4. Route-to-sub-phase mapping (D-004) is now fully built except 4F:
   knowledge->4C, safety->4D, combined_safety_maintenance->4D,
   maintenance->4E all done. `process_optimization` is the **only** route
   still on the 4B stub (`app/agents/nodes/stubs.py`), and is 4F's job.
5. S1-S7 schema field lists are pinned in `app/schemas/agent_outputs.py`
   (all seven defined already, in 4C) — do not re-read
   `docs/model-evaluation-spec.md`; the shapes are already available by
   import.
6. The evaluation-asset hash guard is
   `backend/tests/test_evaluation_asset_guard.py` (D-003) — must pass,
   unchanged, at the end of every sub-phase. Still pinned to
   sha256=beb507819082539dcdbf3c5b1ff1e30a5590cd071258af6ca8ec475d7f23e0b4;
   unchanged through 4E.
7. Shared infrastructure now available to 4F, built during 4C-4E:
   - `refuse()` / `enforce_citations()` /
     `enforce_citations_and_authorization_language()` /
     `enforce_citations_and_diagnostic_language()` / `EnforcementFailure`
     (base) / `CitationEnforcementFailure` (subclass) in
     `app/agents/enforcement.py`.
   - `app/agents/safety_language.py`'s `find_authorization_language()` —
     4F's brief explicitly says to reuse 4D's authorisation-language
     validator, not reimplement it; use
     `enforce_citations_and_authorization_language()` directly, exactly as
     `nodes/safety.py` does.
   - `app/agents/prompts/shared.py::format_evidence_block()` — reused by
     `prompts/knowledge.py`, `prompts/safety.py`, `prompts/maintenance.py`;
     4F should use it too rather than defining a fourth copy.
   - `build_graph(session=...)` / `run_graph(query, session=...)` session
     threading (D-008) — add `"process_optimization"` to `graph.py`'s
     `route_nodes` dict the same way the other four were.
   - `app.services.sparse.identifiers()` for deterministic equipment-tag
     extraction from free text (D-011), if 4F's trend analysis needs to
     scope to a specific asset.
8. Local commits are permitted and expected at each sub-phase boundary
   (message form `phase4f: <summary>`, etc.). Never push.
9. **When 4F is complete, this is the LAST sub-phase.** Per
   `docs/phase4-autonomous-continuation.md` section 9, write
   `docs/phase4-summary.md` next (per-sub-phase status, the full decision
   log with HIGH-priority entries first, every `TODO(PROVISIONAL)` in the
   tree, anything `BLOCKED`/`INCONCLUSIVE` — note D-015 already needs
   listing there — and measured latency), then **stop**. Do not begin
   Phase 5.
10. 4F builds the process optimization agent (S6, S7) per
    `docs/phase4-autonomous-continuation.md` section 8:
    - Confounder acknowledgement in trend analysis (a differential-
      pressure-rose-but-flow-also-rose shape) — surface competing
      explanations rather than asserting causation from correlation. No
      existing deterministic validator for this in the tree; it is
      necessarily a prompt-level instruction (there is no way to code-
      verify "did the model consider a confounder" the way citation
      validity or authorisation language can be checked), so lean on a
      fixture test with two co-moving variables and assert the response
      surfaces both, plus a clear self-audit note that this property is
      prompt-enforced, not code-enforced, unlike every other sub-phase's
      headline property.
    - Every set-point/valve-position suggestion carries
      `action_class: "process_change"` and `human_approval_required: true`,
      phrased as a proposal — **reuse 4D's `_harden_action_recommendation`-
      style override pattern** (see `app/agents/nodes/safety.py`) rather
      than trusting the model, and **reuse
      `enforce_citations_and_authorization_language()`** directly (D-004's
      own text: "Reuse 4D's authorisation-language validator here").
    - Arithmetic stays in Python — reuse `compute_sensor_features`
      (already built, 4B) and `sensor_features_query`'s trend features
      (`SensorFeatureSummary.slope`/`percentage_change`/etc, already
      computed deterministically) rather than asking the model to compute
      a trend statistic itself.

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
- D-015 (MEDIUM, but noted for completeness): `test_query`'s live-model
  call is INCONCLUSIVE in this sandbox after three attempts, all failing
  with a ~160s model-gateway timeout — not a code defect, but the operator
  should re-run it against a warmed, adequately-resourced model runtime to
  confirm the live path genuinely works end to end before relying on this
  test's coverage.
