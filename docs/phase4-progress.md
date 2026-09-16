# Phase 4 autonomous run — progress

Last updated: 2026-09-17T00:00:00Z (updated at each boundary)
Current sub-phase: 4D
Current unit: 1 of N — not started

## Status
| Sub-phase | Status | Tests | Self-audit | Commit | Notes |
|---|---|---|---|---|---|
| 4A | COMPLETE | (pre-existing) | — | (pre-existing, prior session) | Model gateway; see docs/phase4a.md |
| 4B | COMPLETE | 169 | PASS | (this session) | Retroactive report; see docs/phase4b.md, docs/phase4b-validation.md |
| 4C | COMPLETE | 210 (+41) | PASS | (this session) | Knowledge agent; see docs/phase4c.md, docs/phase4c-validation.md |
| 4D | NOT_STARTED | | | | |
| 4E | NOT_STARTED | | | | |
| 4F | NOT_STARTED | | | | |

## Resume instructions for a fresh session

1. Read this file and `docs/phase4-decisions.md` fully before acting.
2. Do not restart 4B or 4C — both are complete, tested (210 tests total),
   documented (`docs/phase4b*.md`, `docs/phase4c*.md`), and their self-audit
   gates passed.
3. If `Current sub-phase` above is `IN_PROGRESS`, resume from `Current unit`
   — do not re-derive decisions already logged in `docs/phase4-decisions.md`.
4. Route-to-sub-phase mapping is fixed by D-004: knowledge->4C (done),
   safety->4D, maintenance->4E, process_optimization->4F,
   combined_safety_maintenance->4D (reusing 4E's read tools),
   guardrail_refusal/clarification handled by `app/agents/nodes/terminal.py`
   (done in 4C, D-004/D-006).
5. S1-S7 schema field lists are pinned in `app/schemas/agent_outputs.py`
   (all seven defined already, in 4C) — derived only from
   `docs/model-evaluation-spec.md` lines 91-121, never from the case table
   further down. Do not re-read that file; the shapes are already available
   by import.
6. The evaluation-asset hash guard is
   `backend/tests/test_evaluation_asset_guard.py` (D-003) — must pass,
   unchanged, at the end of every sub-phase. Still pinned to
   sha256=beb507819082539dcdbf3c5b1ff1e30a5590cd071258af6ca8ec475d7f23e0b4;
   unchanged through 4C.
7. Shared infrastructure now available to 4D-4F, built during 4C: the
   non-model `refuse()` S5 helper and `enforce_citations()` in
   `app/agents/enforcement.py` (D-006); `build_graph(session=...)` /
   `run_graph(query, session=...)` session threading (D-008) — a
   session-needing node is wired into `graph.py`'s `route_nodes` dict the
   same way `knowledge_node` is.
8. Local commits are permitted and expected at each sub-phase boundary
   (message form `phase4c: <summary>`, etc.). Never push.
9. 4D builds the safety & incident agent (S7, S5) per
   `docs/phase4-autonomous-continuation.md` section 6: an
   authorisation-language validator (deterministic, code-level, rejecting
   phrasings like "you are cleared to" / "permission granted" / "authorised
   to"), conservative escalation on ambiguous severity, `action_class` +
   `human_approval_required` on every action-adjacent proposal, and no
   authorisation implication from `access_scope`. `combined_safety_maintenance`
   also routes here (D-004), reusing 4E's read-only sensor/maintenance tools
   once 4E exists — if 4D is built before 4E, `combined_safety_maintenance`
   may need to fall back to 4D's own safety-only evidence gathering first
   and be revisited once 4E's tools are confirmed reusable; log that as a
   decision if it happens.

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
