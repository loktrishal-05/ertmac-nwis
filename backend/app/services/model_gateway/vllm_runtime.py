"""Registered vLLM placeholder.

MODEL_RUNTIME=vllm is a real, discoverable choice — never a silent fallback to
Ollama — but it is not implemented in Phase 4A. See docs/phase4a.md for the
documented-not-implemented request/response mapping; the exact structured-
output parameter must be confirmed against the vLLM version actually deployed,
at the time it is deployed, not guessed here.

`chat()`'s `think` parameter is Ollama-specific wire semantics (see
ollama_runtime.py); it is accepted here (via **kwargs) but not yet mapped.
A future vLLM implementation should either ignore it or map it onto whatever
reasoning-mode control that vLLM version exposes (vLLM has historically used
different mechanisms across versions — a `chat_template_kwargs` field or a
model-specific `extra_body` parameter — so this must be confirmed against the
deployed version, exactly like the structured-output parameter above."""


class VLLMRuntime:
    name = "vllm"

    def __init__(self, settings):
        self._settings = settings

    def chat(self, **kwargs):
        raise NotImplementedError("MODEL_RUNTIME=vllm is not implemented in Phase 4A")

    def health(self):
        raise NotImplementedError("MODEL_RUNTIME=vllm is not implemented in Phase 4A")

    def list_models(self):
        raise NotImplementedError("MODEL_RUNTIME=vllm is not implemented in Phase 4A")
