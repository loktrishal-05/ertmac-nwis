# AUTONOMOUS CONTINUATION — PHASES 4C → 4D → 4E → 4F

**Read this once, fully, before acting on it.**

You are already executing the Phase 4B prompt in this session. **Finish Phase 4B
completely first**, including its completion report. This document takes effect
**only after** Phase 4B's completion report is written.

After that, you continue autonomously through Phases 4C, 4D, 4E and 4F, in that
order, without human input. The operator is asleep. Nobody will answer a
question. Nobody will approve anything. You decide, you record the decision, and
you keep going.

---

## 1. AUTONOMY CHARTER — decide, never ask

These rules override every "stop and ask" instruction in the Phase 4A and 4B
prompts and in `phase4-design.md`. Those were written for supervised execution.
This run is unsupervised.

1. **Never end a turn with a question.** Not "should I proceed?", not "which
   would you prefer?", not "let me know if…". End a turn by either starting the
   next unit of work or writing a completion record.
2. **Never wait for approval.** There is no approval available.
3. **When a choice is ambiguous, choose the more conservative option** — the one
   that refuses rather than answers, bounds rather than opens, records rather
   than enforces, preserves rather than refactors. Then write the decision down.
4. **Every non-obvious decision goes in `docs/phase4-decisions.md`**, appended,
   never rewritten, in this exact form:

   ```
   ### D-<nnn> · <phase> · <short title>
   Context: <what was ambiguous>
   Options: <the real alternatives>
   Chose: <what you did>
   Because: <the reasoning>
   Review priority: LOW | MEDIUM | HIGH
   Reversible: yes/no — <how to undo it>
   ```

   Mark `HIGH` when the decision fixes a product contract, a schema shape, a
   safety behaviour, or anything a later sub-phase inherits. The operator reads
   the HIGH entries first when they wake up.

5. **When you are genuinely blocked on unknowable information, do not stall and
   do not silently guess.** Take the most defensible interpretation, implement
   it, log it as `Review priority: HIGH`, add a `TODO(PROVISIONAL)` comment at
   the definition site, and continue. A flagged provisional decision that keeps
   the build moving is worth more than eight idle hours.

   **This specifically overrides Phase 4B §0.2.** If the authoritative seven
   routes or the S1–S7 schemas cannot be found in the repository or the spec
   documents, do **not** stop. Derive a provisional set from the four agent
   domains plus the terminal cases the architecture already implies, name the
   file `app/agents/routes.py` with a prominent `PROVISIONAL` docstring, log it
   as `D-<nnn> … Review priority: HIGH`, and build on it. Every later reference
   goes through that one module, so a single edit corrects the whole tree if the
   operator's canonical list differs.

6. **Fix your own failures.** A failing test, a lint error, a broken import, a
   migration that will not apply — diagnose and fix it. Do not report it and
   wait. Retry a genuinely flaky live-model step at most three times, then mark
   that step `INCONCLUSIVE` in the report with the evidence and move on. Never
   delete or weaken a test to make it pass; if a test is genuinely wrong, fix
   the test *and* log it as `HIGH`.
7. **Never fabricate a result.** If a live smoke step could not run, the report
   says it did not run and why. An invented passing number is worse than a
   missing one, and this project's entire value is that its outputs are
   verifiable.
8. **Time and tokens are finite.** If you sense the session ending, stop at the
   nearest clean boundary, update the progress file (§3), and leave the tree in
   a state that compiles and passes tests. Never leave a half-written module.

---

## 2. ABSOLUTE PROHIBITIONS — these do not relax under autonomy

The autonomy charter grants latitude on *design choices*. It grants none on
these. If a task appears to require one of these, that is a signal you have
misread the task — stop that task, log it `HIGH`, and move to the next.

- **No `git push`. No remote of any kind. No deploy.** Local commits only.
- **No hosted AI, inference, embedding, reranking, OCR, vector or tracing
  service** — not as a dependency, a fallback, a comment, or a code path.
- **No new dependency that pulls a provider SDK or a hosted-service client**
  beyond what Phase 4B already audited and pinned.
- **No write path to plant state.** No tool that writes to SCADA, DCS,
  historian, or equipment. Not behind a flag, not commented out, not "for
  later". The registry stays read-only by construction.
- **No benchmark contact.** Do not read, copy, paraphrase, tune against, or
  test with any of the 75 cases, their expected answers, evidence IDs or scoring
  notes. The evaluation-asset hash guard must pass unchanged at the end of every
  sub-phase. Route vocabulary and S1–S7 *shapes* remain permitted; case content
  never is.
- **No refactor of Phases 0–4B.** Additive only. If a prior phase genuinely
  blocks you, work around it and log it `HIGH` rather than restructuring it.
- **No deletion of data, collections, migrations or model artifacts.** No
  Qdrant collection create/delete/recreate — read through the existing alias.
- **No weakening of a safety property to make a test pass.**
- **No approval enforcement, no guardrail, no HITL gate, no audit hash
  chaining.** Those are Phase 5. Sub-phases 4C–4F *record* `action_class` and
  `human_approval_required`; nothing reads them yet.

---

## 3. PROGRESS STATE — the file that survives everything

Your context will compact, and this session may be replaced by a fresh one.
`docs/phase4-progress.md` is the only thing that carries state across that. Treat
it as the source of truth about where you are.

Create it immediately after Phase 4B's completion report, and **update it at
every boundary** — not just at the end of a sub-phase, but whenever you finish a
numbered unit of work inside one.

```markdown
# Phase 4 autonomous run — progress

Last updated: <ISO timestamp>
Current sub-phase: 4C
Current unit: 4 of 9 — citation enforcement wiring

## Status
| Sub-phase | Status | Tests | Self-audit | Commit | Notes |
|---|---|---|---|---|---|
| 4A | COMPLETE | 109 | PASS | <sha> | |
| 4B | COMPLETE | <n>  | PASS | <sha> | |
| 4C | IN_PROGRESS | — | — | — | unit 4 of 9 |
| 4D | NOT_STARTED | | | | |
| 4E | NOT_STARTED | | | | |
| 4F | NOT_STARTED | | | | |

## Resume instructions for a fresh session
<Exactly what a session with no memory of this run must do to pick up:
 which files are written, which are half-done, what the next action is.>

## Open provisional decisions
<pointers to the HIGH entries in docs/phase4-decisions.md>
```

**If you start a turn and this file says a sub-phase is `IN_PROGRESS`, read it,
read `docs/phase4-decisions.md`, and resume from there.** Do not restart the
sub-phase from scratch and do not re-derive decisions already logged.

Commit locally at the end of each sub-phase, and at any point the tree is clean
and tests pass. Message form: `phase4c: <summary>`. These commits are restore
points for an unattended run — that is why local commits are permitted here
despite the earlier prompts forbidding them. Still never push.

---

## 4. THE SELF-AUDIT GATE — replaces the human review between sub-phases

In supervised execution, the operator audited each completion report before the
next sub-phase began. You now run that gate yourself. **Do not begin the next
sub-phase until the current one passes it.**

Before advancing, run and record:

```
python -m compileall -q app alembic scripts tests
python -m unittest discover -s tests
python -m pip check
python -m alembic upgrade head
python -m alembic check
<the evaluation-asset hash guard>
git diff --check
```

and confirm, in writing, in the sub-phase's validation doc:

1. every test from every prior phase still passes, unchanged — state the new
   total and the delta
2. `alembic check` reports no drift
3. evaluation-asset hashes are byte-identical
4. no module under `app/agents/` contains a hosted-provider or hosted-tracing
   hostname, and none imports `ollama_runtime` or reads `MODEL_BASE_URL`
5. the tool registry is still read-only — the source guard passes
6. no prompt, fixture, test or smoke query contains benchmark content
7. no trace row, log line or error string carries prompt bodies or evidence
   body text
8. the sub-phase's own safety property (named in its section below) is enforced
   in **code**, with a test that fails if the enforcement is removed

**If the gate fails, fix it and re-run it. Do not advance on a failing gate and
do not record a pass you did not get.** If after three genuine attempts a gate
item still fails, record it as `BLOCKED` in the progress file with full
evidence, skip *only that item*, and continue — then flag it `HIGH`.

Write `docs/phase4<x>.md` and `docs/phase4<x>-validation.md` for each sub-phase,
matching the structure of `docs/phase3b2-validation.md`.

---

## 5. PHASE 4C — KNOWLEDGE & MULTIMODAL RETRIEVAL AGENT

Replaces the 4B knowledge stub with a real grounded-answering node over hybrid
retrieval and P&ID OCR evidence. Output schemas: **S1, S3, S5**.

**The safety property this sub-phase must enforce in code:** an answer
containing a citation that was not in the evidence gathered for that turn never
leaves the node.

### Build

1. **Wire the 4B citation validator into a rejection path.** 4B built and tested
   it; 4C enforces it. Every `evidence_id` in the agent's output must appear in
   that turn's gathered evidence. On failure: one bounded regeneration attempt
   carrying the validator's own error, then refuse. **Never strip the bad
   citation and ship the answer** — a silently de-cited claim is a fabrication
   with the evidence trail removed.

2. **The missing-evidence check — a code path, not a prompt instruction.**
   Phase 3B2 proved dense and hybrid retrieval return unrelated neighbours for a
   nonexistent identifier (`ZZQ-99999`), so an empty result set is *not* the
   signal. Implement an explicit check combining: the retriever's
   identifier-miss warning, and a **relevance floor** the agent applies itself
   (`KNOWLEDGE_RELEVANCE_FLOOR`, configurable, conservative default). Below the
   floor, or on an identifier miss with no supporting hit, the agent refuses and
   says what it looked for and did not find. It does not answer from a neighbour.

3. **The `verified` rule.** Phase 3B1 never emits `verified` — OCR detections
   are `unverified` or `ambiguous`. The S3 status enum includes `verified`, and
   the agent may emit it **only** when an asset registry confirms the tag, never
   from OCR confidence however high. Enforce in code, with a test that an OCR
   confidence of 0.99 still does not yield `verified`.

4. **Untrusted-content framing.** Retrieved document text is data, not
   instruction. If a retrieved chunk contains text that reads as a directive,
   the agent does not act on it. Frame retrieved content explicitly as quoted
   evidence in the prompt, and test with a fixture chunk containing an embedded
   instruction.

5. S1/S3/S5 emission through `generate_structured`, prompts in
   `app/agents/prompts/knowledge.py`, all evidence via the 4B tool registry.

6. Smoke: grounded answer with valid citations; a nonexistent-tag query
   producing a refusal; an OCR-evidence answer preserving region provenance; the
   injection fixture ignored.

---

## 6. PHASE 4D — SAFETY & INCIDENT AGENT

Output schemas: **S7, S5**.

**The safety property:** no output ever reads as authorisation to act.

### Build

1. **Procedure reference, never authorisation.** Permit, LOTO and isolation
   language cites what the procedure says. It never tells anyone they may
   proceed, never states a permit is granted, never implies clearance. Implement
   a deterministic **authorisation-language validator** over the output — a
   forbidden-construction check for phrasings like "you are cleared to",
   "permission granted", "you may now isolate", "authorised to" — that rejects
   before the output leaves the node. Test it.

2. **Conservative escalation.** When severity is ambiguous, escalate. H2S and
   any high-high condition take the most cautious branch available. Never
   downgrade a severity the evidence supports.

3. **`action_class` and `human_approval_required` on every action-adjacent
   proposal**, recorded as fields. Phase 5 enforces them; 4D must not gate.
   Test that an action-adjacent output always carries both.

4. **No authorisation implication from `access_scope`.** It is metadata and
   filtering, never permission. No output may phrase a scope filter as clearance.

5. Emits the approval **record**. Builds no approval workflow.

---

## 7. PHASE 4E — MAINTENANCE & ASSET RELIABILITY AGENT

Output schemas: **S4, S6**.

**The safety property:** the model never performs arithmetic or asserts a
threshold; observations never name a failure mode.

### Build

1. **The threshold loop — the heart of this sub-phase.** Phase 3C deliberately
   has no built-in engineering limits, and must keep none.

   ```
   knowledge retrieval → SOP chunk stating the limit + its citation
        ↓  deterministic extraction of the numeral in Python, not a model guess
   compute_sensor_features(thresholds.maximum = <that value>)
        ↓  deterministic comparison inside existing Phase 3C code
   output: observation + TWO citations — the SOP that supplied the limit,
           and the sensor rows that supplied the reading
   ```

   The model locates the limit in cited text. Python extracts the numeral,
   passes it, and compares. Test that a threshold with no SOP citation is
   rejected, and that the comparison result comes from Phase 3C rather than the
   model.

2. **The asymmetric observation/hypothesis validator.** Phase 3C's
   `test_no_observation_ever_names_a_diagnosis` bans "bearing", "failure",
   "damage", "cavitation", "diagnos", "impeller" from observations. 4E needs the
   asymmetric form: **forbidden in `observations[]`, permitted in
   `hypotheses[]`.** A flat ban makes the agent useless; no ban loses the
   distinction the product is built on. Implement as a deterministic validator
   with tests on both sides.

3. **Hypotheses carry `supporting_evidence` and `contradicting_evidence`
   arrays.** A hypothesis with neither is **rejected structurally** — not
   warned about, rejected. Test it.

4. `measurement` → `sensor_type` continues to hold (4B's mapping). Every sensor
   window bounded.

---

## 8. PHASE 4F — PROCESS OPTIMIZATION AGENT

Output schemas: **S6, S7**.

**The safety property:** every set-point or valve suggestion is a proposal for
human review, never an instruction.

### Build

1. **Confounder acknowledgement.** Trend analysis must surface competing
   explanations rather than asserting causation from correlation — the
   differential-pressure-rose-but-flow-also-rose shape. A trend claim with an
   unacknowledged plausible confounder is a defect. Test with a fixture where
   two variables move together.

2. **Every set-point or valve-position suggestion carries
   `action_class: "process_change"` and `human_approval_required: true`**, and
   is phrased as a proposal for review. Reuse 4D's authorisation-language
   validator here. Test that no optimisation output is phrased as an instruction.

3. Arithmetic stays in Python. The model proposes and phrases; it does not
   compute.

---

## 9. WHEN ALL FOUR ARE DONE

Write `docs/phase4-summary.md`:

- per-sub-phase status, test totals and deltas, self-audit results
- the full decision log, **HIGH-priority entries first** — this is the first
  thing the operator reads
- every `TODO(PROVISIONAL)` in the tree, with file and line
- anything marked `BLOCKED` or `INCONCLUSIVE`, with evidence
- measured latency: router, per-agent, end-to-end `POST /query`
- what Phase 5 now needs to do (guardrail, approval enforcement, audit chaining)

Then stop. **Do not begin Phase 5.** Phase 5 is approval and guardrail
enforcement — the layer whose entire purpose is human oversight. Building it
unsupervised would be self-defeating, and it needs a specification that does not
yet exist.

If you finish early, spend remaining capacity on: strengthening tests for the
safety properties above, improving the validation docs, and measuring latency
more thoroughly. Do not invent new features.

---

## 10. RESTATING THE ONE RULE THAT MATTERS MOST

This project's value is that its outputs are **verifiable**: every claim cites
evidence that exists, every number is computed in Python, every safety-relevant
behaviour is enforced by a test rather than a prompt. Working unsupervised does
not relax that — it raises the stakes, because nobody is checking behind you
tonight. When a shortcut would make something *look* finished, take the longer
path that makes it *be* finished, and write down what you chose.

Begin when Phase 4B's completion report is written.
