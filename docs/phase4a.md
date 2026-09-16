# Phase 4A — Local model gateway

This phase adds a two-layer local model gateway: a **Gateway** that owns
policy (defaults, retries, structured-output repair, tool-call protocol
conformance) and a **Runtime** that owns transport (the actual wire protocol
to one local inference server). Agents in later phases import only the
Gateway — never a runtime module directly — so the underlying inference
engine can be swapped (Ollama today, a vLLM-compatible server later) without
touching a single agent.

**Phase 4A implements only the Model Gateway box** of the target architecture:

```text
React → FastAPI → LangGraph → Agent Nodes → Model Gateway → Local Runtime
                                              (Ollama now, vLLM-compatible later)
```

No LangGraph, no agents, no tool executor, and no answer-generation endpoint
exist yet. The only new route is `GET /models/status`. n8n is untouched.

## Reasoning ("thinking") mode — measured, not assumed

The installed `qwen3.5:9b` build is a reasoning-capable model that defaults
to emitting an extended "thinking" trace before its answer. Measured live
against this model on this development machine:

| Call | think (default) | think=False |
| --- | --- | --- |
| Plain one-word reply | 41.8s, 131 reasoning tokens, correct answer | 1.2s, 2 tokens, correct answer |
| Schema-constrained extraction, 256-token budget | **160s, `content` empty, `done_reason=length` — the entire budget was consumed by the reasoning trace before any JSON was emitted. Schema validation fails outright.** | 12.0s, valid schema-conformant JSON |

This is not merely a latency cost: with the default reasoning mode on, a
bounded-budget structured-output call can fail completely rather than
degrade gracefully, because Ollama's `format`-constrained decoding does not
apply to the (unconstrained) thinking trace — it can consume the entire
`num_predict` budget on its own. Raising the token budget large enough to
outlast an unpredictable reasoning trace is not a reliable fix for a request
that must return promptly.

**Response:** a `think: bool | None = None` parameter now runs end to end —
`ModelGateway.generate_text` / `generate_structured` / `generate_with_tools`
→ the `ModelRuntime.chat()` Protocol → `ollama_runtime.py`, the only place
that maps it onto Ollama's wire-level `think` field. `None` (the default)
sends nothing and leaves the runtime's own default unchanged — **no default
behavior changed** by adding this parameter. `vllm_runtime.py`'s docstring
notes the field is Ollama-specific wire semantics that a future
implementation should ignore or map onto whatever reasoning control that
vLLM version exposes.

**What Phase 4A deliberately does not do:** decide a default `think` value
for agents, or make the gateway silently pass `think=False` on the caller's
behalf. That is a policy decision about prompt/response shape, and per this
phase's own rule the gateway owns no prompts and no policy — it only makes
the control available. See "Phase 4B blocker" in Limitations.

## Why the two-layer split matters

If agent code imported Ollama's client directly, "swap the runtime" would
mean editing every agent. Instead:

- `app/services/model_gateway/base.py` defines a `ModelRuntime` Protocol with
  no runtime-specific vocabulary in it at all — no wire field names, no
  endpoint paths, no runtime's own name.
- `app/services/model_gateway/ollama_runtime.py` is the **only** file that
  knows Ollama exists: it is the sole place mapping the gateway's
  runtime-agnostic `chat()` call onto `POST /api/chat` and back.
- `app/services/model_gateway/gateway.py` (the facade agents import) talks
  only to the Protocol. It is equally free of runtime-specific vocabulary.
- A source-guard test (`tests/test_model_gateway.py::SourceGuardTests`)
  enforces this at every run, so the claim can't quietly rot as the codebase
  grows: `gateway.py` and `base.py` are scanned for Ollama wire-protocol
  tokens (word-boundary matched so a false positive like "formatting" in a
  docstring can't accidentally trip it), and every `model_gateway/*.py` file
  **except** `registry.py` (which *is* the hosted-provider denylist, and
  necessarily names those hosts to reject them) is scanned for a hosted AI
  provider hostname.

**The gateway owns no prompts.** It never injects a system message, safety
preamble, or formatting instruction of its own. The one exception is the
structured-output repair turn, which relays nothing more than the schema
validator's own error message — see below.

## Package layout

```text
backend/app/services/model_gateway/
    __init__.py          public exports only
    types.py              DTOs (Pydantic v2, extra="forbid")
    errors.py             exception hierarchy
    base.py                ModelRuntime Protocol
    schemas.py             Pydantic -> JSON Schema, $defs inlining, fence stripping, validation
    registry.py             runtime selection + URL/host policy (allowlist + denylist)
    ollama_runtime.py       the ONLY file that knows Ollama exists
    vllm_runtime.py         registered placeholder, raises NotImplementedError
    gateway.py              the facade agents import
```

## Configuration

Root `.env` / environment settings:

| Variable | Default | Meaning |
| --- | --- | --- |
| MODEL_RUNTIME | ollama | `ollama` or `vllm` (vLLM raises `NotImplementedError`) |
| MODEL_BASE_URL | http://127.0.0.1:11434 | Must satisfy both the allowlist and the denylist |
| MODEL_NAME | *(none — required)* | No default anywhere in the tree; empty fails startup |
| MODEL_ALLOWED_HOSTS | 127.0.0.1,localhost,::1,ollama,vllm,model-runtime | Comma-separated host allowlist |
| MODEL_CONNECT_TIMEOUT_SECONDS | 5 | Matches the existing DB connect-timeout convention |
| MODEL_TIMEOUT_SECONDS | 120 | Warm-call read timeout |
| MODEL_FIRST_LOAD_TIMEOUT_SECONDS | 600 | Used by `health()` and the first call after process start |
| MODEL_MAX_RETRIES | 2 | Connect errors, read timeouts, and 502/503/504 only |
| MODEL_TEMPERATURE | 0.0 | Deterministic by default |
| MODEL_SEED | 42 | |
| MODEL_CONTEXT_WINDOW | 8192 | |
| MODEL_MAX_OUTPUT_TOKENS | 1024 | |
| MODEL_KEEP_ALIVE | 30m | Ollama-specific; read only inside `ollama_runtime.py` |
| MODEL_STRUCTURED_REPAIR_ATTEMPTS | 1 | At most one repair turn |
| MODEL_LOG_PROMPTS | false | When false (the default), logs never contain prompt bodies |

### MODEL_NAME has no default

A guessed tag that happens to exist would silently benchmark the wrong
model. `MODEL_NAME` is validated at `Settings()` construction time (process
startup); an empty value is a hard failure whose message tells the operator
to run `ollama list` and set the tag explicitly. `scripts/smoke_model_gateway.py`
additionally confirms the configured tag is actually installed (a live check
config-time validation cannot perform) and prints every installed tag if not.

### Two independent host controls

1. **Allowlist** — `MODEL_BASE_URL`'s host must appear in `MODEL_ALLOWED_HOSTS`
   (`app/services/model_gateway/registry.py::validate_model_url`).
2. **Denylist** — independently of the allowlist, the same function rejects
   `api.openai.com`, `api.anthropic.com`, `generativelanguage.googleapis.com`,
   `api.cohere.ai`, `api.mistral.ai`, `api.together.xyz`, `openrouter.ai`,
   `api.groq.com`, any `*.azure.com` host, and any `bedrock*.amazonaws.com`
   host.

These are deliberately redundant: even if `MODEL_ALLOWED_HOSTS` were edited
to include a hosted-provider host by mistake, the denylist still rejects it.
A one-line allowlist edit alone is not enough to break the project's
sovereignty claim. Both checks run inside `Settings.validate_model_gateway`
(a `model_validator(mode="after")`), so a bad configuration fails at process
startup, never mid-request.

### No request-supplied routing

Every DTO in `types.py` uses `extra="forbid"`. No caller can smuggle `model`,
`base_url`, `runtime`, `api_key`, or `endpoint` through a `ChatMessage` or
`ToolSpec` — those fields are always rejected by validation, tested by exact
field name.

## Structured-output contract

```text
schema.model_json_schema() → inline every $defs/$ref → pass as the runtime's
constrained-decoding schema → strip one leading/trailing ```json fence
→ json.loads → schema.model_validate()
```

- **`$defs` inlining is mandatory.** Pydantic emits `$ref` for any nested
  model, and every later agent schema is nested. `json_schema_for()` resolves
  every reference recursively so the runtime always receives a self-contained
  schema with no `$defs` section.
- **Fence stripping** removes one full wrapping ` ```json ... ``` ` (or bare
  ` ``` `) block. It does **not** extract an embedded `{...}` from
  surrounding prose — prose outside the JSON object is a parse failure to be
  reported, not something to salvage.
- **Repair policy:** on a validation failure (malformed JSON or a schema
  mismatch), the gateway appends exactly two messages — the model's own
  broken output, then a message containing only the validator's own error
  text and an instruction to respond again with corrected JSON. No hint, no
  example, and never the expected value. At most `MODEL_STRUCTURED_REPAIR_ATTEMPTS`
  (default 1) such turns run.
- **Final failure** raises `StructuredOutputError`, which preserves the raw
  model text (`.raw_text`) and the validator's error text (`.validation_errors`)
  for the caller to log or inspect. There is no partial-success return value.
- No new dependency: Pydantic is used for both schema generation and
  validation.

**Constrained decoding guarantees syntax, not truth.** A schema-valid object
can still contain a fabricated citation or an invented value — the runtime
only guarantees the *shape* of the output matches the schema, never that its
*content* is grounded in anything real. Verifying that a value is actually
supported by retrieved evidence is Phase 4B/4C work, not this module's job.

## Ollama request/response mapping

Endpoint: `POST /api/chat`, always with `"stream": false`.

| Gateway concept | Ollama field |
| --- | --- |
| messages | `messages` |
| json_schema | `format` (only present when a schema was supplied) |
| tools | `tools` (only present when tools were supplied) |
| temperature / seed / stop | `options.temperature` / `options.seed` / `options.stop` |
| max_output_tokens | `options.num_predict` |
| context_window | `options.num_ctx` |
| MODEL_KEEP_ALIVE | `keep_alive` |
| think | `think` (only present when explicitly set; omitted entirely when `None`) |
| `message.content` | → `GenerationResult.text` |
| `message.tool_calls[]` | → `ToolCall` list (a missing `id` is synthesized as `call_<index>`) |
| `done_reason` | → `finish_reason` (`length`/`stop`/`other`; forced to `tool_calls` whenever tool calls are present) |
| `prompt_eval_count` / `eval_count` | → `usage.prompt_tokens` / `usage.completion_tokens` |
| `total_duration`, `load_duration`, `prompt_eval_duration`, `eval_duration` | → timings, **nanoseconds converted to milliseconds** |

Two behaviors are never silent:

- `done_reason == "length"` sets `truncated=True` **and** appends a warning.
  A silently truncated response looks like a model-quality problem and would
  waste real debugging time.
- A missing model tag raises `ModelUnavailableError` **listing every
  currently installed tag**, recovered via a follow-up `GET /api/tags` call —
  never a silent substitution of a different model.

## Errors, timeouts, and retries

```text
ModelGatewayError
├── ModelConfigurationError     (also a ValueError, so Settings validation
│                                wraps it into pydantic.ValidationError like
│                                every other Settings-time failure)
├── ModelUnavailableError       connect refused / DNS failure / model tag absent / 404
├── ModelTimeoutError           connect or read deadline exceeded
├── ModelRuntimeError           runtime 5xx, or a malformed response envelope
├── StructuredOutputError       still schema-invalid after the bounded repair
├── ModelOutputTruncatedError   done_reason == "length" where the caller forbade it
└── ToolCallProtocolError       a tool name outside the supplied specs, or unparseable arguments
```

Two timeouts: **connect** (`MODEL_CONNECT_TIMEOUT_SECONDS`, default 5s,
matching the existing DB-connection convention) and **read**. The read
timeout is `MODEL_FIRST_LOAD_TIMEOUT_SECONDS` (default 600s) for `health()`
and for the gateway's first chat call after process start (a cold model load
can take minutes on CPU), and `MODEL_TIMEOUT_SECONDS` (default 120s) for
every call after that — tracked per `ModelGateway` instance via a `_warmed_up`
flag, not per Ollama request.

Retries (`MODEL_MAX_RETRIES`, default 2) use exponential backoff with jitter,
bounded by a **total wall-clock deadline** computed once per call — so
retries can never turn one timeout into six minutes. Only connect errors,
read timeouts, and runtime 502/503/504 are retried. A 4xx is **never**
retried (it is a deterministic rejection that needs a human, and retrying it
would only hide that), and `StructuredOutputError` is never retried at the
transport level — schema repair is a separate, explicitly bounded path, and
stacking the two would multiply calls silently.

**Redaction:** with `MODEL_LOG_PROMPTS=false` (the default), nothing in this
package logs a prompt body — only message counts, roles, character counts,
model name, timings, and bounded error excerpts (`raw_response_excerpt` is
capped at 2000 characters). Later phases will put Confidential SOP and
incident text into prompts; a log file is an export path like any other.

## vLLM — documented, not implemented

`MODEL_RUNTIME=vllm` is a real, discoverable choice: `registry.get_runtime`
constructs a `VLLMRuntime`, and every one of its methods raises
`NotImplementedError("MODEL_RUNTIME=vllm is not implemented in Phase 4A")` —
never a silent fallback to Ollama.

The mapping below is **documented for a future implementer, not implemented
now**, because the exact parameter names must be confirmed against whichever
vLLM version is actually deployed, at the time it is deployed — writing a
guess into code today risks shipping a plausible-looking but wrong mapping:

| Gateway concept | vLLM (OpenAI-compatible server) |
| --- | --- |
| chat | `POST /v1/chat/completions` |
| list models | `GET /v1/models` |
| health | `GET /health` |
| max_output_tokens | `max_tokens` |
| context_window | a **server launch flag**, not a request field |
| MODEL_KEEP_ALIVE | not applicable (no equivalent unload-on-idle concept) |
| usage | `usage.prompt_tokens` / `usage.completion_tokens` |
| structured output | vLLM has offered more than one mechanism over time — an OpenAI-style `response_format` with a JSON-schema form, and a guided-decoding parameter passed via `extra_body`. **Confirm the exact parameter against the deployed vLLM version before implementing.** |
| think | Ollama-specific wire semantics (see above). Ignore, or map onto whatever reasoning-mode control the deployed vLLM version exposes — confirm at implementation time. |

## `GET /models/status`

Read-only, `503` when the runtime is unreachable (matching the existing
dependency-failure convention used by `/knowledge/retrieve` and the Phase 3C
maintenance/sensor routes). Returns runtime name, reachability, runtime
version, configured model, whether it is present, available models, loaded
models, and the deterministic settings currently in force (temperature,
seed, context window, max output tokens). Never returns `MODEL_BASE_URL`, a
credential, or any prompt text — there is no generation endpoint in Phase 4A,
so there is nothing else to expose.

## Limitations

- **`ModelInfo` doesn't model VRAM or expiry.** `GET /api/ps` returns richer
  per-loaded-model fields (`size_vram`, `expires_at`) than the shared
  `ModelInfo` DTO carries; `OllamaRuntime.loaded_models()` maps what fits and
  drops the rest. The smoke script reads the raw runtime response for the
  fuller detail rather than widening the shared DTO for one runtime's extra
  fields.
- **PHASE 4B BLOCKER: someone must decide the default `think` value for
  agents.** The gateway now exposes `think` end to end, but Phase 4A
  deliberately sets no policy on when to use it — the gateway owns no
  prompts and no policy, and picking a default reasoning-mode stance for
  agent calls is exactly that. Measured on the installed `qwen3.5:9b`: with
  the runtime's own default (reasoning on), a bounded-budget
  schema-constrained call **failed outright** (empty content) after 160s;
  with `think=False` the identical call succeeded in 12s. Phase 4B's agent
  loop cannot safely default to Ollama's own behavior for structured/tool
  calls without hitting this failure mode — see
  `docs/phase4a-validation.md` for the full comparison and every other
  measured latency number.
- **No streaming.** Every call sets `"stream": false"`. Time-to-first-token
  is therefore always `None` in `GenerationTimings` — it is only meaningful
  for a streamed call, and Phase 4A never streams.
- **Not tested on GPU-only or multi-GPU hardware.** Validation ran on a
  single consumer GPU with partial VRAM offload (see the validation report
  for the exact split); full-GPU and CPU-only configurations were not
  separately measured.
- **No grounding validation.** Constrained decoding guarantees schema-valid
  JSON, never a *true* JSON — a structurally valid object can still contain a
  fabricated value. That check belongs to a later phase.
