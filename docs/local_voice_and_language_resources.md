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

**Initial D-LIVE baseline — 2026-09-28 (PARTIAL; repair results below).** Local STT/TTS and authenticated HTTP integration
are working. Synthetic Hindi/Tamil recognition and technical identifier review
did not meet the intended validation: missing or malformed tags can escape the
existing pattern-based review. No Phase D application logic was changed.

### Installed runtime and hardware

- Windows 11 Home Single Language 10.0.26200; i5-12450H; 16,852,574,208 bytes RAM
  (15.70 GiB); RTX 2050, 4096 MiB VRAM.
- Existing Python 3.11, 3.14 and another project's managed 3.12 were found. Speech
  uses its own Python 3.11 venv, separate from the backend environment.
- Docker Desktop's PostgreSQL 17 and Qdrant were already healthy. FFmpeg 8.1.2
  and Ollama with `qwen3.5:4b` and `qwen3.5:9b` were already installed; unchanged.
- STT: faster-whisper 1.2.1, CTranslate2 4.8.2, PyAV 18.1.0;
  `Systran/faster-whisper-small`, multilingual, CPU/int8, four inference threads,
  beam size 3. English/Hindi/Tamil are explicitly selected, without translation
  or identifier prompts. No CUDA libraries or second ASR model were installed.
- TTS: eSpeak NG 1.52.0, voices `en-us`, `hi`, `ta`; compact formant synthesis,
  not a neural voice model. All three produced nonempty PCM WAV locally.
- Disk: model directory 463.69 MiB, speech venv 299.31 MiB, extracted eSpeak
  directory 23.73 MiB (includes installer copy), source MSI 12.17 MiB: about
  798.90 MiB total logical file size. No large hosted or multilingual neural TTS stack.
- Observed speech-process peak working set 709.47 MiB; peak Windows committed
  memory 2869.63 MiB. Budget approximately 3 GiB RAM headroom for these short
  requests, not a guaranteed upper bound. A one-second STT CPU sample was 253.1%
  (psutil sums logical cores). No speech GPU allocation is required; total GPU
  memory was 62 MiB before and 70 MiB during the sample, with 0% GPU utilization.
  Concurrent Qwen latency was not benchmarked.

Upstream compatibility references: [faster-whisper CPU/int8 and Python support](https://github.com/SYSTRAN/faster-whisper),
[eSpeak languages](https://github.com/espeak-ng/espeak-ng/blob/master/docs/languages.md),
[eSpeak 1.52.0 release](https://github.com/espeak-ng/espeak-ng/releases/tag/1.52.0).

### Exact Windows provisioning and launch

PowerShell, repository root. These are the completed provisioning steps, provided
for reproduction; do not download again on this machine. Downloads contact public
package/model repositories only during provisioning, never for speech inference.

```powershell
Set-Location 'C:\Users\Lohith k\Desktop\sovereign-agentic-workbench'
py -3.11 -m venv models/local-speech/.venv
& models/local-speech/.venv/Scripts/python.exe -m pip install --only-binary=:all: faster-whisper==1.2.1 ctranslate2==4.8.2 av==18.1.0 fastapi==0.141.1 uvicorn==0.54.0 psutil==7.2.2
& models/local-speech/.venv/Scripts/python.exe -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-small', revision='536b0662742c02347bc0e980a01041f333bce120', local_dir='models/local-speech/faster-whisper-small', allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.txt'])"
Invoke-WebRequest https://github.com/espeak-ng/espeak-ng/releases/download/1.52.0/espeak-ng.msi -OutFile models/local-speech/espeak-ng.msi
$installer = (Resolve-Path models/local-speech/espeak-ng.msi).Path
$target = Join-Path (Get-Location) 'models/local-speech/espeak'
Start-Process msiexec.exe -ArgumentList @('/a', ('"' + $installer + '"'), '/qn', ('TARGETDIR="' + $target + '"')) -WindowStyle Hidden -Wait
Get-FileHash models/local-speech/espeak-ng.msi -Algorithm SHA256
Get-FileHash models/local-speech/faster-whisper-small/model.bin -Algorithm SHA256
& models/local-speech/.venv/Scripts/python.exe backend/scripts/local_speech_runtime.py
```

Expected SHA-256 values:

```text
espeak-ng.msi  7f673c709ea5dd579d3b5ebb98688cc575328a6ab7438d2bc405b88cedaeafb9
model.bin     3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671
```

The wrapper sets `ESPEAK_DATA_PATH` to the extracted data directory. Without it,
the portable Windows executable crashed while locating its data. No system-wide
TTS installation or service was needed. The wrapper binds only `127.0.0.1:8765`,
disables Hugging Face network/model downloads, requires local model files,
rejects browser Origin headers and non-loopback clients, and stores no audio.
One STT request runs at a time; a concurrent request gets HTTP 503/text fallback.

In a second PowerShell window:

```powershell
Set-Location 'C:\Users\Lohith k\Desktop\sovereign-agentic-workbench'
$env:WORKBENCH_STT_URL = 'http://127.0.0.1:8765/stt'
$env:WORKBENCH_TTS_URL = 'http://127.0.0.1:8765/tts'
& backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

These two URL settings were also saved in the existing ignored root `.env`.
The existing 30-second speech timeout remains unchanged. This wrapper accepts
WAV, WebM/Opus, Ogg/Opus and MP4/AAC (when available in the provisioned PyAV build),
up to 4 MiB/60 decoded seconds, and TTS text up to 2000 characters including
the application's advisory prefix. Other containers or longer text fail to the
existing editable-text/text fallback. The browser's WebM path is not validated.

### Reproduce the controlled validation

With the speech runtime and existing PostgreSQL running:

```powershell
Set-Location 'C:\Users\Lohith k\Desktop\sovereign-agentic-workbench\backend'
& .venv/Scripts/python.exe -m unittest discover -s tests -p test_local_voice.py
& .venv/Scripts/python.exe -m unittest discover -s tests -p test_advanced_c.py
& .venv/Scripts/python.exe scripts/smoke_local_speech.py
```

Result: 17 Phase D tests and 25 Advanced-C tests passed. The live script starts
the real backend on a temporary loopback port with a temporary PostgreSQL schema,
uses a random-password requester and real login, checks `/product/status`, calls
both voice HTTP routes, logs out, stops that backend and drops its schema. It
never calls `/query`, BLIND, or an LLM. The ordinary backend was subsequently
started separately on `127.0.0.1:8000` using the configured root `.env`.

Authenticated status returned `stt_health: ready`, `tts_health: ready`, and
`text_mode: true`. Legacy `stt`/`tts` fields remain `configured_unverified` by
design. Local detailed results, including word probabilities, are in ignored
`data/dlive-results.json`; backend startup diagnostics are in
`data/dlive-backend.log`. Audio stays in memory and is discarded, with no
microphone capture or temporary audio files to clean up.

### Actual synthetic results

Audio was generated by eSpeak from exactly these public synthetic strings.
This is a TTS-to-STT integration check, not a human-speech accuracy benchmark.
Each row is one trial; latency includes HTTP and backend audit overhead for STT.

| Language | Input | Actual transcript | Audio duration | STT latency | Direct TTS latency |
| --- | --- | --- | ---: | ---: | ---: |
| English | Pump P-204A vibration is elevated. | pump P204A vibration is elevated. | 3.97 s | 6.07 s | 0.151 s |
| Hindi | पंप P-204A का कंपन बढ़ा हुआ है। | पुंप भीवो सो चारे का कुम्पन बरहा भुवेया | 3.96 s | 7.03 s | 0.168 s |
| Tamil | P-204A பம்பின் அதிர்வு அதிகமாக உள்ளது. | பிரிந்துவிடாங்கு ஏற்பாம் விடாதி விடாதிகமாக உள்ளாது | 3.98 s | 7.43 s | 0.099 s |
| Identifiers (English) | P-204A. XV-204D. SOP-P204-001. 7.1 mm/s. | P204A Roman 15204D SOC P204-001 7.1mm-S | 10.17 s | 6.38 s | 0.133 s |

Identifier results:

- `P-204A` became `P204A`; Hindi/Tamil lost it. None received an identifier-specific flag.
- `XV-204D` became `Roman 15204D`; no identifier-specific flag. eSpeak's reading
  of `XV` is also a possible contributor, so this trial cannot isolate ASR error.
- `SOP-P204-001` became `SOC P204-001`; no identifier-specific flag.
- `7.1 mm/s` became `7.1mm-S`. The adapter detected the substring `7.1mm` and
  flagged it with `low_word_confidence`; it did not recover the intended unit.

Every transcript was returned verbatim with `confirmation_required: true` and
editable text. No tag was automatically repaired or inserted. **The intended
identifier correction coverage therefore failed for the first three tags.**
The adapter's overall confidence was null. The engine did return uncalibrated
word probabilities on the separate identifier repeat: `P204A` 0.583, `Roman`
0.239, `15204D` 0.789, `SOC` 0.491, `P204` 0.850, `-001` 0.965, `7` 0.826,
`.1mm` 0.815, `-S` 0.356. Do not interpret these as recognition accuracy.

TTS returned playable-container PCM WAV for all three languages. Application
response text was byte-for-byte unchanged; the speech input retains the existing
advisory prefix. Adapter TTS latency was 0.471/0.677/0.656 seconds for en/hi/ta,
and 0.719 seconds for the identifier sentence. Pronunciation and spoken semantic
fidelity were not certified by a listener; the poor round-trip recognition is
not a formal audio-quality metric. French returned `unsupported_language` with
the original text and text fallback; the wrapper independently rejected it
with HTTP 422. Invalid audio and browser-origin requests were also rejected.

Security checks: speech traffic used loopback only; observed runtime sockets were
all loopback. Source inspection confirmed subprocess eSpeak and local CTranslate2
inference with offline model loading, no hosted client or proxy. This is not a
packet-capture audit. No hosted speech, confidential inputs, microphones, API
secrets or committed models were used. No benchmark artifacts were modified by
D-LIVE, and no commit was made.

## D-LIVE repair validation — 2026-09-28

**D-LIVE RELEASE READY for mandatory human-reviewed transcription.** This is
readiness of the local adapter and correction warnings, not an accuracy
certification for Hindi/Tamil or industrial identifiers.

The existing Phase D adapter now adds deterministic structural review warnings.
It never calls an LLM, consults a plant registry, rewrites the transcript or
invents a replacement tag. `text` and `original_text` remain the runtime output.
Each warning retains `text`, `start`, `end`, and `reasons`, and adds `raw_span`,
`review_required: true`, `confirmation_required: true`, and `candidates: []`.
There are deliberately no candidate suggestions without a verified registry.
The response-level `review_required` indicates detected spans; the existing
`confirmation_required` remains true for **every** transcript. A general
`review_message` also warns the caller to verify tags, documents and measurements.
Absence of a specific span warning does not certify correctness.

Detection reuses the equipment/instrument patterns, relaxing only bounded
hyphen/space separators: `P204A`, `P 204 A`, `P-204 A`, `P204-A`, `XV204D`,
`XV 204 D`, and analogous established prefixes. Document detection accepts
bounded numeric components beside established document prefixes, including
`WO7745`, `WO 7745`, `SOP P204-001`, and `SOP-P204 001`. One character substitution
in a document prefix is suspicious only alongside that numeric structure:
`SOC P204-001` is flagged, never interpreted as a particular intended prefix.
An orphan numeric/suffix token such as `15204D` gets a fragment warning, never an
inferred `XV` prefix. Damaged rate separators such as `7.1mm-S`, and explicit
spoken measurements such as `7 point 1 millimeters per second`, require review.
Well-formed identifiers retain the existing confidence/case checks.

### Whisper-small comparison and decision

The installed 1.2.1 signature and [versioned upstream source](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py)
confirm support for language, beam size, temperature, VAD, initial prompt and
hotwords. The wrapper already passed `hi` and `ta` correctly; tests now verify
both adapter-to-runtime and runtime-to-model propagation.

Three profiles were evaluated on identical in-memory eSpeak audio per sentence:

- Baseline: beam 3, default temperature fallback `[0, .2, .4, .6, .8, 1]`, no VAD.
- Deterministic/VAD: beam 5, temperature 0, VAD enabled.
- Generic context: deterministic/VAD plus a short language-specific maintenance
  vocabulary prompt (pump, valve, vibration, work order; English also SOP).

All used `condition_on_previous_text=False` and word timestamps. No actual tag
answers, plant data, or confidential vocabulary were put in a prompt. Hotwords
are supported but were not used to seed the expected identifiers. Results did
not establish a reliable improvement; **baseline decoding is retained**, with
VAD/prompt/hotwords disabled explicitly. Neither Whisper small nor eSpeak was
replaced, and no additional package or model was downloaded for the repair.

| Language/profile | Actual transcript | Direct decoding latency |
| --- | --- | ---: |
| Hindi / baseline | पुंप भीवो सो चारे का कुम्पन बरहा भुवेया | 3.242 s |
| Hindi / deterministic-VAD | पुंप भीवो सो चारे का कम पुंपर हाँ आजेया | 4.276 s |
| Hindi / generic context | पंप भीवल सो चारे का कंपन बरहाव आदेश। | 7.732 s |
| Tamil / baseline | பிரிந்துவிடாங்கு ஏற்பாம் விடாதி விடாதிகமாக உள்ளாது | 6.806 s |
| Tamil / deterministic-VAD | பிரிந்துவிடாங்கு ஏற்பம் விடாடி விடாடிக்கமாக உள்ளாடு. | 6.650 s |
| Tamil / generic context | பிருடுத்துவிடாங்கு ஏற்பம் விடாதி, விடாதிகமாக உள்ளாது. | 8.212 s |

Expected Hindi/Tamil sentences are unchanged from the baseline table above.
The context trial changed words but did not recover the tags. eSpeak formant
speech, mixed-script tag pronunciation, and Whisper decoding can all contribute;
this experiment cannot separate them. No native-speaker listening assessment or
human-audio accuracy benchmark was performed. Do not generalize these results
to Whisper accuracy on naturally spoken Hindi or Tamil.

Reproduce the comparison from the repository root:

```powershell
& models/local-speech/.venv/Scripts/python.exe backend/scripts/evaluate_local_speech.py
```

All 12 actual trial transcripts, options and timings are saved to ignored
`data/dlive-decoding-comparison.json`; no audio is persisted.

### Repaired live adapter results

Authenticated `/product/status`: `stt_health=ready`, `tts_health=ready`, text
fallback enabled. The controlled live smoke script validates the new warning
spans, text equality and nonempty, fully readable 16-bit PCM WAV returned by
the backend in English, Hindi and Tamil. It also checks unsupported-language
fallback, invalid WAV rejection and browser-origin rejection. Temporary backend,
login and schema are cleaned up; the ordinary backend and speech runtime were
restarted on loopback ports 8000 and 8765 with the repaired code.

| Input | Actual transcript | STT latency | Specific review |
| --- | --- | ---: | --- |
| Pump P-204A vibration is elevated. | pump P204A vibration is elevated. | 5.455 s | `P204A`: malformed identifier |
| पंप P-204A का कंपन बढ़ा हुआ है। | पुंप भीवो सो चारे का कुम्पन बरहा भुवेया | 6.827 s | Tag absent; general confirmation warning only |
| P-204A பம்பின் அதிர்வு அதிகமாக உள்ளது. | பிரிந்துவிடாங்கு ஏற்பாம் விடாதி விடாதிகமாக உள்ளாது | 7.207 s | Tag absent; general confirmation warning only |
| P-204A. XV-204D. SOP-P204-001. 7.1 mm/s. | P204A Roman 15204D SOC P204-001 7.1mm-S | 6.697 s | All four damaged spans flagged |

For the identifier sentence the exact warnings were `P204A` (malformed identifier),
`15204D` (possible fragment), `SOC P204-001` (possible document prefix), and
`7.1mm-S` (suspicious engineering unit). The original low-confidence `7.1mm`
substring warning is also retained. No candidate replacement was supplied.

TTS direct latency: en 0.117 s, hi 0.095 s, ta 0.109 s, identifiers 0.135 s.
Backend TTS latency: 0.522/0.462/0.506/0.576 s respectively. Response text was
unchanged and unsupported French retained the original text. WAV validity is
verified; pronunciation and spoken semantic fidelity are not certified.
The updated smoke script writes `data/dlive-repair-results.json`, preserving
the original `data/dlive-results.json` baseline.

Validation: six new deterministic tests cover the requested malformed forms,
valid tags, raw preservation, confirmation/no invented candidates, no correction
network call, Hindi/Tamil hints reaching the model, and STT/TTS failure fallback.
The targeted voice/routing/governance/security run passed 139 tests with 22
PostgreSQL-gated skips. The subsequent full backend run enabled those PostgreSQL
checks: **857 passed, 0 failed, 0 errors, 1 skipped (858 total, 223.775 s)**.
The remaining skip is the opt-in live model test; BLIND was not run.
`git diff --check` passed. Detailed local logs and exact counts are retained in
`data/dlive-repair-targeted.log`, `data/dlive-repair-full.log`, and
`data/dlive-repair-full-summary.json`.

```powershell
# New deterministic checks, from backend:
& .venv/Scripts/python.exe -m unittest discover -s tests -p test_voice_identifier_review.py
# Full backend including isolated PostgreSQL checks, excluding the opt-in live model check:
$env:WORKBENCH_TEST_POSTGRES = '1'
$env:WORKBENCH_TEST_LIVE_MODEL = '0'
& .venv/Scripts/python.exe -m unittest discover -s tests
```

Repair security: no hosted speech, confidential data, audio persistence,
speech credentials, LLM correction, external speech request or non-loopback
binding. Only synthetic test text is recorded in the local result files.
No frontend, Phase E worktree, frozen benchmark asset or commit was changed.
The benchmark readiness report was already dirty before this task; its SHA-256
was recorded as `922203145d57d18f00d283c29832f1392f421d06f40a190bf4193b6841556ec2`.

## Limitations

- Synthetic live integration is measured above; human-speech accuracy and spoken
  semantic fidelity remain unmeasured. Hindi/Tamil synthetic recognition was poor.
- Identifier detection is pattern-based: completely omitted tags, plausible but
  wrong canonical tags, and unknown formats can escape specific warnings.
  Ambiguous numeric/suffix tokens can cause false positives. Human confirmation
  is mandatory; a warning is not proof of a particular intended identifier.
- No translation. A future translator must return `original_text` and
  `translated_text` separately and leave identifiers unchanged.
- Audio is limited to 4 MiB per request (short utterances); there is no streaming.
- DNS locality is checked before dispatch; it does not defend against DNS
  rebinding between the check and the connection.
