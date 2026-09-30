# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- Plant engineers, operators and maintenance staff at industrial sites who ask questions of their own procedures, drawings, sensor data and maintenance history (requester role).
- Reviewers and administrators who approve or reject advisory recommendations and audit what happened (reviewer / admin roles, assigned by the server).
- Hackathon judges and evaluators, who meet the product first through the public landing page and a guided walk through the workbench. (Confirmed: the landing page must impress judges.)

## Product Purpose

Sovereign AI Workbench is an on-premise, governed industrial intelligence workbench. It answers questions with cited evidence from locally indexed documents, P&IDs, sensor readings and maintenance records; anything that could influence operations is held as a draft for human approval; every decision joins a hash-linked audit chain. Success is a trustworthy, fast, legible answer that a human can verify and govern, with no data leaving the site.

## Positioning

Local, sovereign and governed by construction: inference runs on the site's own hardware (Ollama, qwen3.5:9b and qwen3.5:4b), hosted AI calls in the confidential path are zero, recommendations are advisory only and never operate equipment, and human approval plus a tamper-evident (not tamper-proof) audit chain govern every operational draft.

## Operating Context

- Query workspace (text and local voice in English, Hindi and Tamil), with H3 human review of every voice transcript before submission.
- Evidence: SOPs and manuals, P&ID drawings (as-drawn evidence only, never proof of plant state), sensor readings, maintenance work orders, operator notes.
- Governance: approval queue, durable executions, audit log with chain verification, sovereignty proof.
- Deployment: Docker backend with PostgreSQL, Qdrant, local speech and Ollama; offline-capable, not automatically air-gapped.

## Capabilities and Constraints

- Frontend: React 19, Vite 7, React Router 8, GSAP 3 (+ @gsap/react). No Tailwind, no overlapping animation libraries. WebGL is written as raw shaders with no new dependency (confirmed).
- Landing and authentication may be dark, glowing, WebGL-heavy and cinematic. The authenticated `/app/*` workbench stays mild, light, calm and professional (confirmed).
- Charts, boards and metrics show live backend data only; empty states where nothing exists; no fabricated values (confirmed).
- Self-service sign-up, email/OTP recovery and Google sign-in are disabled until the separate auth backend reports those capabilities; the UI must stay honest about that.
- Approval decisions happen only through the review flow; no drag-to-approve or other shortcut that bypasses it.
- Undecided: auth backend capabilities (being built in a separate worktree), P&ID viewer and maintenance workspace (planned F6), administration (planned F7).

## Brand Commitments

- Name: Sovereign AI Workbench. Approved assets: `frontend/public/assets/branding/` (Sovereign mark, horizontal/stacked/primary logos, app icons; agent mark) and the three approved auth videos in `frontend/public/assets/auth/`. Logos are used as supplied, never redrawn.
- Voice: precise, sober, evidence-first; claims must be verifiable (e.g. "not automatically air-gapped", "tamper-evident, not tamper-proof").

## Evidence on Hand

- Verified facts (September 2026): 0 hosted AI calls in the confidential path, 2 local models, 3 languages, 890 automated backend tests, 75-case benchmark, 168 hash-verified frozen benchmark files.
- Dev database holds synthetic, cited records: sensor readings (e.g. P-204 vibration), maintenance work orders (e.g. WO-7714), audit events, pending approvals.
- Absent and never to be fabricated: customer names, testimonials, deployments, performance numbers beyond the facts above, live integrations with BHASHINI / API Setu / DigiLocker.

## Product Principles

1. Evidence before answers: every claim shows where it came from.
2. Humans govern: advisory output only; approval is explicit and audited.
3. Sovereign by default: local inference, no silent network dependency.
4. Honest state: loading, empty, unavailable and planned are always stated plainly.
5. Calm under pressure: the workbench is built for long shifts, not spectacle.

## Accessibility & Inclusion

- Multilingual UI and evidence (English, हिन्दी, தமிழ்); original-language text shown exactly.
- Keyboard operable, visible focus, reduced-motion and Save-Data respected, WCAG AA contrast on workbench surfaces.
