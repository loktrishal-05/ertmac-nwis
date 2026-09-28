# Local Voice and Government Language Resources (Phase D)

Phase D finishes the existing Advanced-C voice subsystem
(`app/services/local_voice.py`, `/voice/transcribe`, `/voice/synthesize`,
`/product/status`). It adds no second voice stack and no new query path.

## Confidential speech path

```
microphone / audio file (browser, base64)
  -> POST /voice/transcribe  (authenticated; local STT only)
  -> editable transcript + flagged identifiers (nothing is submitted automatically)
  -> POST /query {input_channel: "voice", input_language}  (same preflight, routing, LangGraph, governance, HITL)
  -> text answer
  -> optional POST /voice/synthesize  (local TTS; presentation only)
```

Speech never bypasses `/query`: the transcript is only a proposal that the user
edits and submits as text. The same applies to `/executions` (A2 durable runs),
which accept the same `QueryRequest`.

## Local runtime contract

The adapters are engine-neutral. Any local engine (for example a Whisper-family
STT or a Piper/Indic TTS model) sits behind a small HTTP shim:

| Call | Request | Response |
| --- | --- | --- |
| `POST WORKBENCH_STT_URL` | `{audio_base64, mime_type, language}` | `{text, confidence?, words?: [{text, confidence}], language?}` |
| `POST WORKBENCH_TTS_URL` | `{text, language}` | `{audio_base64, mime_type}` |
| `GET <origin>/health` | none | HTTP 200 when ready |

- Endpoints must be loopback or private addresses (`app/core/locality.py`), are
  resolved before dispatch, and are called with `trust_env=False` (no proxies)
  and no redirects. Credentials, query strings, fragments and public hosts are
  rejected. Responses are capped at 6 MiB.
- `WORKBENCH_SPEECH_TIMEOUT_SECONDS` (default 30, max 120) bounds each call; the
  health probe uses at most 5 seconds.
- Models are never downloaded at runtime. Provisioning is an operator task.
- `/product/status` keeps `stt`/`tts` (`configured_unverified` or `unavailable`,
  unchanged for the current frontend) and adds `stt_health`/`tts_health`
  (`ready` or `unavailable`, from a live local probe).

## Fallback behaviour

| Condition | STT result | TTS result |
| --- | --- | --- |
| not configured / non-local URL | `unavailable`, `reason: not_configured` | same |
| runtime down / HTTP error | `reason: runtime_unavailable` | same |
| timeout | `reason: timeout` | same |
| malformed runtime output | `reason: invalid_response` | same (bad audio is never returned) |
| policy denial | `reason: policy_denied` | same |
| unsupported language | transcript metadata `effective: "und"` | `status: unsupported_language`, runtime not called |

STT failure returns `fallback: "editable_text"`; the user types instead. TTS
failure returns `fallback: "text"` and the original answer text unchanged. There
is exactly one local attempt and never a hosted fallback. A speech failure
happens before any query, so no workflow action exists to duplicate.

## Languages

English (`en`), Hindi (`hi`) and Tamil (`ta`), including region tags such as
`hi-IN`. The requested language goes to the runtime; the transcript is returned
as recognised (`original_text`). Translation is disabled
(`translation: disabled_original_preserved`, `translated_text: null`), so evidence
quotes are never translated. `input_language` and `input_channel` are stored with
the governed request and bind replay. Actual Hindi/Tamil quality depends
entirely on the provisioned local model.

## Technical identifier preservation

Transcripts are never rewritten. `technical_identifiers` lists what was detected,
with character offsets:

- equipment tags (`P-204A`) and instrument tags (`XV-204D`), from the existing `PID_PATTERNS`;
- document, SOP and work-order IDs (`SOP-P204-001`, `WO-7745`, plus `DOC`, `MOC`, `PTW`, `WI`, `DWG`);
- numeric values with engineering units (`7.1 mm/s`, `bar`, `°C`, `rpm`, `mg/L`, and so on).

`identifier_review` lists what a human must check before submitting:

- `low_word_confidence`: an identifier overlaps a recognised word below `WORKBENCH_STT_IDENTIFIER_MIN_CONFIDENCE` (default 0.85);
- `low_transcript_confidence`: no word timings were given and overall confidence is low;
- `non_canonical_case`: for example `p-204b`;
- `possible_split_identifier`: for example `P 204 A`. It is never joined automatically; this form also reads as `204 A` (amperes), which is exactly the ambiguity a human resolves.

TTS sends the answer text unchanged, after a fixed advisory prefix.

## Government resource policy

`app/services/language_resources.py` classifies every language resource:

| Classification | Confidential plant/company data | Public, non-confidential data |
| --- | --- | --- |
| `LOCAL_APPROVED` | allowed | allowed |
| `PUBLIC_EXTERNAL_OPTIONAL` | never | only when explicitly enabled |
| `DISABLED_FOR_CONFIDENTIAL_DATA` | never | never |

All workbench speech endpoints are server-classified `CONFIDENTIAL`. Clients
cannot choose a provider or a data classification: unknown request fields are
rejected. `LOCAL_APPROVED` requires a named approver, and for a downloaded
artifact a pinned SHA-256; an `external_api` entry can never be `LOCAL_APPROVED`.

### BHASHINI

BHASHINI (https://bhashini.gov.in) is registered as `PUBLIC_EXTERNAL_OPTIONAL`.

- `WORKBENCH_BHASHINI_ENABLED` defaults to `false`.
- Even when enabled, policy permits it only for `PUBLIC` data, never `CONFIDENTIAL`.
- This build ships **no BHASHINI network client**: a permitted selection still
  raises `PolicyDenied` ("not implemented"), so no code path can send data to it.
- No BHASHINI credentials are defined or committed. A future public-only client
  would need its own review, secret handling outside the repository, and
  provenance naming BHASHINI on every result.
- Local execution of BHASHINI-compatible models has **not** been tested here. To
  evaluate one locally, download it under its published licence, record it in the
  registry below as `local_downloaded`, pin its SHA-256, serve it behind the local
  runtime contract, and mark it `LOCAL_APPROVED` only after review.

### AIKosh resource registry

AIKosh-catalogued models and datasets can be evaluated through an
operator-maintained JSON registry (`WORKBENCH_LANGUAGE_RESOURCE_REGISTRY`), a list of:

```json
{"name": "…", "provider": "AIKosh", "source": "catalogue reference or local path",
 "license": "as published for the resource", "intended_use": "…",
 "deployment": "local_downloaded | external_api",
 "classification": "DISABLED_FOR_CONFIDENTIAL_DATA", "approved_by": null, "artifact_sha256": null}
```

- Nothing is scraped or downloaded automatically. Entries are references only and
  never an authority source for plant knowledge.
- New entries default to `DISABLED_FOR_CONFIDENTIAL_DATA` until the licence,
  provenance and a locally measured evaluation are reviewed.
- No specific AIKosh resource is listed or claimed here; each needs its own
  licence and suitability review.
- `/product/status` lists every registry entry with its classification and
  confidential eligibility.

## Routing (A1)

Model selection reads only the transcript text and trusted risk signals;
`select_model` has no channel or language parameter. A safety or evidence
question routes to `qwen3.5:9b` whether typed or spoken. Hindi/Tamil text is
non-ASCII, which also forces the primary model.

## Durability (A2)

After transcription a spoken request is an ordinary `QueryRequest`, so durable
execution, checkpoints and resume work unchanged. STT and TTS are stateless,
single calls outside the graph and create no governance or execution records.

## Knowledge and governance (Phase C)

Saying "approve this" or "mark verified" is only query text. Approval,
verification, revocation and gap resolution need the authenticated reviewer
APIs. `/query` rejects extra fields (for example `speaker_role`, `verified` or
`governance_status`) and accepts only `input_channel` values `text` and `voice`.

## Security and retention

- Audio: base64 is validated, limited to 1 byte–4 MiB, restricted to one of five
  MIME types, and the container signature must match the declared type (WAV
  RIFF/WAVE, WebM EBML, Ogg, MPEG, MP4 `ftyp`). Runtime-returned audio is checked
  the same way.
- No filenames or paths are accepted, and no temporary files are created: audio
  is handled in memory only and discarded after the request (`audio_retention: none`).
- Transcripts and synthesized text are not stored by the speech endpoints.
  Their audit events record only kind, language, status, reason, provider,
  identifier counts and latency; never audio, transcript or answer text.
- A submitted transcript becomes a normal `/query`, retained exactly like typed
  queries under the existing governance and trace settings.
- Responses carry `Cache-Control: no-store`. The routes require an authenticated
  requester, reviewer or admin.
- SSRF: only configured loopback/private endpoints are reached; client input
  never supplies a URL.

## Live validation

No local STT or TTS runtime is installed on this workstation (no speech engine
packages or binaries, and no speech service on local ports; Ollama serves only
the text models). Live STT and TTS checks are therefore **NOT AVAILABLE**. All
behaviour is covered by deterministic tests against an in-process mocked runtime
(`tests/test_local_voice.py`). To go live, provision a local engine behind the
contract above and set `WORKBENCH_STT_URL` / `WORKBENCH_TTS_URL`.

## Limitations

- Recognition quality, Hindi/Tamil accuracy and identifier accuracy are
  unmeasured until a local model is provisioned and evaluated on synthetic or
  public audio.
- Identifier detection is pattern-based; unfamiliar identifier formats are not flagged.
- No translation. A future translator must return `original_text` and
  `translated_text` separately and leave identifiers unchanged.
- Audio is limited to 4 MiB per request (short utterances); there is no streaming.
- DNS locality is checked before dispatch; it does not defend against DNS
  rebinding between the check and the connection.
