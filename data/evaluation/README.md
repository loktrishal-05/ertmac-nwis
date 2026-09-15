# Model Evaluation Pack

Generated from the approved Sovereign Workbench model evaluation specification.

## Contents

- `model_eval_cases.jsonl` — 75 structured evaluation cases.
- `model_eval_config.json` — selected model tiers, runtime settings, run policy, and safety gates.

## Recommended repository placement

Copy these files into:

```text
data/
└── evaluation/
    ├── model_eval_cases.jsonl
    └── model_eval_config.json
```

Keep the original Markdown specification in:

```text
docs/model-evaluation-spec.md
```

## Current selected models

- Development primary: Qwen3.5-9B
- Stronger benchmark: Qwen3.5-35B-A3B
- Low-memory fallback: Qwen3.5-4B

## Immediate use

Do not fine-tune with these cases. They are evaluation-only.

When the LangGraph/model gateway is ready, the benchmark harness should:

1. Load one JSONL case.
2. Clear conversational state.
3. Apply the same system prompt and tool schemas for every model.
4. Record the model's route/tool calls before returning mock tool results.
5. Validate the requested output schema.
6. Validate citation IDs only against supplied evidence.
7. Apply safety-gate checks before aggregate scoring.
8. Run each blind case three times.
9. Record latency, tokens, model/runtime revision, quantization, RAM/VRAM and raw output.

## Current local runtime

Qwen3.5-9B has already been pulled and manually smoke-tested through Ollama on the development machine.
