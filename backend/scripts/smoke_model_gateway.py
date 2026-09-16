"""Opt-in live validation for the Phase 4A local model gateway. Real Ollama,
real network calls, no fake transport.

Benchmark firewall: every prompt here invents fictional content (asset tag
ZZ-9999) that does not appear in data/evaluation/'s 75-case benchmark or its
corpus. Nothing under data/evaluation/ is read by this script.

--fresh is accepted for CLI parity with the other smoke scripts, but is a
no-op here: unlike the PDF/CSV smokes, there is no persistent fixture file to
reuse or regenerate — every invocation is a fresh set of live calls.

THINKING-MODE FINDING (measured live, not assumed): the installed
qwen3.5:9b Ollama build defaults to an extended "thinking" reasoning trace.
With the default (thinking on) and a 256-token budget, a schema-constrained
call returned EMPTY content (done_reason=length) after ~75s on this
machine — the entire token budget went to the reasoning trace and never
reached the JSON. The identical call with think=False returned valid,
schema-conformant JSON in ~12.5s. Every FUNCTIONAL call below therefore
passes think=False. Step 12 reproduces both sides live as a dedicated,
clearly-labeled comparison and records the numbers rather than asserting
either way."""
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from app.core.config import settings
from app.main import app
from app.services.model_gateway import (
    ChatMessage,
    ModelTimeoutError,
    StructuredOutputError,
    ToolSpec,
    get_model_gateway,
)


class SyntheticObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_tag: str
    observed_metric: str
    confidence: float


class SyntheticReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_tag: str
    value: float


class SyntheticNested(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reading: SyntheticReading
    note: str


class LatencyLog:
    """Per-call-type wall-clock seconds, so the report can show min/median/max
    per call type rather than only a run total."""
    def __init__(self):
        self._data = {}

    def record(self, call_type, seconds):
        self._data.setdefault(call_type, []).append(seconds)

    def summary(self):
        return {
            call_type: {
                "count": len(values),
                "min_seconds": round(min(values), 3),
                "median_seconds": round(statistics.median(values), 3),
                "max_seconds": round(max(values), 3),
                "raw_seconds": [round(v, 3) for v in values],
            }
            for call_type, values in self._data.items()
        }


def main():
    "--fresh" in sys.argv  # accepted, intentionally unused; see module docstring
    latency = LatencyLog()
    report = {"steps": {}}

    with TestClient(app):
        gateway = get_model_gateway()

        # Step 0 — discover the model tag; never guess it.
        installed = gateway.list_models()
        installed_names = [m.name for m in installed]
        if settings.model_name not in installed_names:
            raise SystemExit(
                f"MODEL_NAME={settings.model_name!r} is not installed on this Ollama runtime.\n"
                f"Installed tags: {installed_names}\n"
                "Run 'ollama list' and set MODEL_NAME in the root .env to one of them."
            )
        report["steps"]["0_discover"] = {"configured_model": settings.model_name, "installed_tags": installed_names}

        # Step 1 — GET /api/version reachable.
        health = gateway.health()
        assert health.reachable, health.detail
        report["steps"]["1_version"] = {"runtime_version": health.runtime_version}

        # Step 2 — GET /api/tags: MODEL_NAME present; record digest and size.
        assert health.configured_model_present
        configured = next(m for m in installed if m.name == settings.model_name)
        report["steps"]["2_tags"] = {
            "digest": configured.digest, "size_bytes": configured.size_bytes,
            "parameter_size": configured.parameter_size, "quantization": configured.quantization,
        }

        # Step 3 — plain generation. think=False for every functional call (see
        # module docstring); first-call load time reported separately from warm latency.
        prompt = [ChatMessage(role="user", content="Reply with exactly one word: ready.")]
        started = time.perf_counter()
        first = gateway.generate_text(messages=prompt, think=False)
        first_wall_seconds = time.perf_counter() - started
        assert first.text.strip(), "First generation returned no text"
        started = time.perf_counter()
        warm = gateway.generate_text(messages=prompt, think=False)
        warm_wall_seconds = time.perf_counter() - started
        latency.record("plain_generation", warm_wall_seconds)
        report["steps"]["3_generation"] = {
            "think": False,
            "first_call_wall_seconds": round(first_wall_seconds, 3),  # cold/warm-model load; not in the latency buckets
            "first_call_timings_ms": first.timings.model_dump(),
            "warm_call_wall_seconds": round(warm_wall_seconds, 3),
            "warm_call_timings_ms": warm.timings.model_dump(),
            "sample_output": first.text[:200],
        }

        # Step 4 — structured generation against a small non-benchmark schema.
        structured_prompt = (
            "This is a synthetic software-validation fixture, not real plant data, and "
            "ZZ-9999 is an invented test-only tag. From this sentence, extract equipment_tag, "
            "observed_metric, and confidence (a number from 0 to 1): "
            "'Synthetic sensor ZZ-9999 logged a placeholder temperature reading with high "
            "confidence during a software test.'"
        )
        started = time.perf_counter()
        structured = gateway.generate_structured(
            messages=[ChatMessage(role="user", content=structured_prompt)], schema=SyntheticObservation,
            think=False, timeout_seconds=120,
        )
        elapsed = time.perf_counter() - started
        latency.record("structured_output_with_repair" if structured.result.repair_attempts else "structured_output", elapsed)
        report["steps"]["4_structured"] = {
            "think": False, "wall_seconds": round(elapsed, 3),
            "value": structured.value.model_dump(), "repair_attempts": structured.result.repair_attempts,
        }

        # Step 4b — deliberately adversarial prompt to exercise the repair path for
        # real latency data, not just the theoretical "structured_output_with_repair" bucket.
        repair_prompt = (
            "This is a synthetic software-validation fixture, not real plant data; ZZ-9999 is an "
            "invented test-only tag. Extract equipment_tag, observed_metric, and confidence from: "
            "'Synthetic sensor ZZ-9999 logged a placeholder pressure reading, confidence: very high.' "
            "Write the confidence field as the word describing it (e.g. \"very high\"), not a number."
        )
        started = time.perf_counter()
        try:
            forced = gateway.generate_structured(
                messages=[ChatMessage(role="user", content=repair_prompt)], schema=SyntheticObservation,
                think=False, timeout_seconds=180,
            )
            elapsed = time.perf_counter() - started
            latency.record("structured_output_with_repair", elapsed)
            report["steps"]["4b_structured_repair_probe"] = {
                "outcome": "recovered", "wall_seconds": round(elapsed, 3),
                "value": forced.value.model_dump(), "repair_attempts": forced.result.repair_attempts,
            }
        except StructuredOutputError as error:
            elapsed = time.perf_counter() - started
            latency.record("structured_output_with_repair", elapsed)
            report["steps"]["4b_structured_repair_probe"] = {
                "outcome": "failed_after_repair", "wall_seconds": round(elapsed, 3),
                "raw_text": error.raw_text, "validation_errors": error.validation_errors,
            }

        # Step 5 — nested schema, exercising $defs inlining end to end.
        nested_prompt = (
            "Synthetic software-validation fixture only; ZZ-9999 is an invented test-only tag. "
            "Extract a nested object with 'reading' (equipment_tag, value) and 'note' from: "
            "'Fictional test asset ZZ-9999 recorded value 42.0 during a software validation run.'"
        )
        started = time.perf_counter()
        nested = gateway.generate_structured(
            messages=[ChatMessage(role="user", content=nested_prompt)], schema=SyntheticNested,
            think=False, timeout_seconds=120,
        )
        elapsed = time.perf_counter() - started
        latency.record("structured_output_with_repair" if nested.result.repair_attempts else "structured_output", elapsed)
        report["steps"]["5_nested"] = {
            "think": False, "wall_seconds": round(elapsed, 3),
            "value": nested.value.model_dump(), "repair_attempts": nested.result.repair_attempts,
        }

        # Step 6 — tool-call shape check with one trivial, obviously read-only fake tool.
        # No executor exists anywhere in this package; nothing here can be executed.
        tools = [ToolSpec(
            name="lookup_synthetic_fixture",
            description="Read-only lookup of a synthetic test fixture value. Never writes, controls, or executes anything.",
            parameters={"type": "object", "properties": {"tag": {"type": "string"}}, "required": ["tag"]},
        )]
        started = time.perf_counter()
        tool_result = gateway.generate_with_tools(
            messages=[ChatMessage(role="user", content="Call lookup_synthetic_fixture with tag ZZ-9999.")],
            tools=tools, think=False, timeout_seconds=120,
        )
        elapsed = time.perf_counter() - started
        latency.record("tool_call", elapsed)
        report["steps"]["6_tools"] = {
            "think": False, "wall_seconds": round(elapsed, 3),
            "tool_calls": [call.model_dump() for call in tool_result.tool_calls],
            "finish_reason": tool_result.finish_reason,
        }

        # Step 7 — determinism probe. Report, never assert: Ollama gives no cross-batch guarantee.
        determinism_prompt = [ChatMessage(role="user", content="Reply with exactly one word: steady.")]
        started = time.perf_counter()
        det_a = gateway.generate_text(messages=determinism_prompt, think=False)
        latency.record("plain_generation", time.perf_counter() - started)
        started = time.perf_counter()
        det_b = gateway.generate_text(messages=determinism_prompt, think=False)
        latency.record("plain_generation", time.perf_counter() - started)
        report["steps"]["7_determinism"] = {
            "think": False,
            "identical": det_a.text == det_b.text,
            "output_a": det_a.text, "output_b": det_b.text,
            "note": "Ollama makes no cross-batch determinism guarantee; this is a measurement, not an assertion.",
        }

        # Step 8 — deliberate short timeout must raise, never swallow.
        started = time.perf_counter()
        timeout_raised = False
        timeout_detail = None
        try:
            gateway.generate_text(
                messages=[ChatMessage(role="user", content="Write a very long, detailed essay about industrial pump maintenance.")],
                think=False, timeout_seconds=1,
            )
        except ModelTimeoutError as error:
            timeout_raised = True
            timeout_detail = str(error)
        elapsed = time.perf_counter() - started
        latency.record("timeout_probe", elapsed)
        assert timeout_raised, "A 1-second timeout must raise ModelTimeoutError, not silently succeed"
        report["steps"]["8_timeout"] = {"raised": True, "detail": timeout_detail, "wall_seconds": round(elapsed, 3)}

        # Step 9 — GET /models/status through the real FastAPI route.
        with TestClient(app) as client:
            response = client.get("/models/status")
        assert response.status_code == 200, response.text
        report["steps"]["9_models_status_route"] = response.json()

        # Step 10 — GET /api/ps: loaded model, VRAM, and expiry (raw runtime call; ModelInfo
        # doesn't model VRAM/expiry — see docs/phase4a.md limitations).
        loaded = gateway._runtime().loaded_models()
        report["steps"]["10_loaded_models"] = [model.model_dump() for model in loaded]

        # Step 11 — hardware/context record.
        report["steps"]["11_hardware_context"] = {
            "platform": platform.platform(), "python_version": platform.python_version(),
            "model_runtime": settings.model_runtime, "model_context_window": settings.model_context_window,
            "model_temperature": settings.model_temperature, "model_seed": settings.model_seed,
            "model_max_output_tokens": settings.model_max_output_tokens,
        }

        # Step 12 — thinking-mode comparison: latency AND schema conformance, on vs off,
        # live and apples-to-apples (same prompt, same token budget on both sides).
        comparison = {}
        plain_prompt = [ChatMessage(role="user", content="Reply with exactly one word: ready.")]
        for label, think_value in (("think_on", True), ("think_off", False)):
            started = time.perf_counter()
            result = gateway.generate_text(messages=plain_prompt, think=think_value, timeout_seconds=180)
            elapsed = time.perf_counter() - started
            comparison[f"plain_generation_{label}"] = {
                "wall_seconds": round(elapsed, 3), "output": result.text[:200],
                "truncated": result.truncated, "completion_tokens": result.usage.completion_tokens,
            }
        for label, think_value in (("think_on", True), ("think_off", False)):
            started = time.perf_counter()
            try:
                result = gateway.generate_structured(
                    messages=[ChatMessage(role="user", content=structured_prompt)], schema=SyntheticObservation,
                    think=think_value, max_output_tokens=256, timeout_seconds=400,
                )
                elapsed = time.perf_counter() - started
                comparison[f"structured_{label}"] = {
                    "wall_seconds": round(elapsed, 3), "outcome": "valid_schema_conformant",
                    "value": result.value.model_dump(), "repair_attempts": result.result.repair_attempts,
                }
            except StructuredOutputError as error:
                elapsed = time.perf_counter() - started
                comparison[f"structured_{label}"] = {
                    "wall_seconds": round(elapsed, 3), "outcome": "schema_validation_failed",
                    "raw_text": error.raw_text, "validation_errors": error.validation_errors,
                }
            except ModelTimeoutError as error:
                elapsed = time.perf_counter() - started
                comparison[f"structured_{label}"] = {
                    "wall_seconds": round(elapsed, 3), "outcome": "timed_out", "detail": str(error),
                }
        report["steps"]["12_thinking_mode_comparison"] = comparison

    report["latency_summary_seconds"] = latency.summary()
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    output_path = settings.data_root / "evaluation/results/phase4a_model_gateway_smoke.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("Phase 4A model gateway smoke validation passed.")
    print(f"  report: {output_path}")
    print(f"  configured model: {settings.model_name}")
    print(f"  first-call wall: {report['steps']['3_generation']['first_call_wall_seconds']}s")
    print("  latency summary (seconds):")
    for call_type, stats in report["latency_summary_seconds"].items():
        print(f"    {call_type}: n={stats['count']} min={stats['min_seconds']} "
              f"median={stats['median_seconds']} max={stats['max_seconds']}")
    print(f"  determinism (identical output twice): {report['steps']['7_determinism']['identical']}")
    print(f"  timeout test raised ModelTimeoutError: {report['steps']['8_timeout']['raised']}")
    print("  thinking-mode comparison:")
    for key, value in report["steps"]["12_thinking_mode_comparison"].items():
        print(f"    {key}: {value.get('outcome', 'n/a')} in {value['wall_seconds']}s")


if __name__ == "__main__":
    main()
