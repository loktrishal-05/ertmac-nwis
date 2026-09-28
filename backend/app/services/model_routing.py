"""Deterministic, server-owned model policy; never an authorization decision."""
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.model_gateway.errors import (
    ModelConfigurationError, ModelRuntimeError, ModelTimeoutError,
    ModelUnavailableError, StructuredOutputError, ToolCallProtocolError,
    ModelOutputTruncatedError,
)

RoutingClass = Literal["FAST_LOW_RISK", "DEEP_EVIDENCE", "SAFETY_CRITICAL", "COMPLEX_SYNTHESIS", "FORCE_PRIMARY"]
BoundedTask = Literal["strategy", "formatting", "schema_transform", "metadata", "classification", "helper_text"]


class RiskSignals(BaseModel):
    """Trusted call-site facts, never fields accepted from an HTTP/model payload."""
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    force_primary: bool = False
    evidence_required: bool = False
    evidence_insufficient: bool = False
    conflicting_evidence: bool = False
    missing_verified_knowledge: bool = False
    document_count: int = Field(default=0, ge=0)
    multiple_documents_required: bool = False
    multi_agent: bool = False
    complex_synthesis: bool = False
    safety_context: bool = False
    approval_bearing: bool = False
    pid_uncertainty: bool = False
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)
    high_risk_tools: bool = False
    critical_tag_verification: bool = False
    previous_fast_failure: bool = False


# These signals only increase caution. Unknown tasks and unbounded input default deep.
_SAFETY = re.compile(r"\b(safety|unsafe|safe|shutdown|startup|start|stop|isola\w*|interlock|loto|permit|scada|dcs|plc|trip|alarm|leak|fire|gas|environment\w*|compliance|emission\w*|effluent|wastewater)\b", re.I)
_PLANT = re.compile(r"\b(plant|sensor|readings?|valve|maintenan\w*|diagnos\w*|repair|recommend\w*|approve\w*|approval|verify|verification|evidence|conflict\w*|ocr|drawing|visual|multimodal|topology|piping)\b|p&?id", re.I)
_MULTI = re.compile(r"\b(synthesi\w*|multi[- ](?:document|agent)|(?:multiple|several|two) (?:documents|manuals|sops))\b|\bcompare\b.*\band\b", re.I)
MAX_FAST_INPUT = 2048
MAX_FAST_OUTPUT = 256


def model_config(settings, role):
    """Validate again because Settings.model_copy and runtime mutation skip validation."""
    from app.services.model_gateway.registry import validate_model_url
    if settings.fast_model != "qwen3.5:4b" or settings.primary_model != "qwen3.5:9b":
        raise ModelConfigurationError("Routing requires the benchmark-approved local 4B/9B profiles")
    if role not in ("fast", "primary") or settings.model_runtime not in ("ollama", "vllm"):
        raise ModelConfigurationError("Invalid local routing profile")
    validate_model_url(settings.model_base_url, settings.model_allowed_hosts_set)
    updates = {"model_name": settings.fast_model if role == "fast" else settings.primary_model}
    if role == "fast":
        updates.update(model_max_retries=0, model_structured_repair_attempts=0)
    return settings.model_copy(update=updates)


def select_model(query, *, task: BoundedTask | None = None, requested_path="BOUNDED_TASK",
                 signals: RiskSignals | None = None, config=None):
    from app.core.config import settings
    config = config or settings
    model_config(config, "primary")
    signals = signals or RiskSignals()
    reasons = []
    classification: RoutingClass = "FAST_LOW_RISK"
    if signals.force_primary or signals.previous_fast_failure:
        classification = "FORCE_PRIMARY"
        reasons += [name for name in ("force_primary", "previous_fast_failure") if getattr(signals, name)]
    if signals.safety_context or signals.approval_bearing or _SAFETY.search(query):
        classification = "SAFETY_CRITICAL"
        reasons += [name for name in ("safety_context", "approval_bearing") if getattr(signals, name)]
        if _SAFETY.search(query): reasons.append("safety_language")
    if signals.multiple_documents_required or signals.document_count > 1 or signals.multi_agent or signals.complex_synthesis or _MULTI.search(query) or requested_path == "MGS_PATH":
        if classification == "FAST_LOW_RISK": classification = "COMPLEX_SYNTHESIS"
        reasons.append("multi_document_or_agent")
    evidence_flags = ("evidence_required", "evidence_insufficient", "conflicting_evidence",
        "missing_verified_knowledge", "pid_uncertainty", "high_risk_tools", "critical_tag_verification")
    evidence = [name for name in evidence_flags if getattr(signals, name)]
    if signals.ocr_confidence is not None and signals.ocr_confidence < 0.6: evidence.append("low_confidence_ocr")
    if _PLANT.search(query): evidence.append("plant_or_evidence_language")
    if evidence or requested_path in ("HYBRID_RAG_PATH", "EXISTING_AGENTIC_PATH"):
        if classification == "FAST_LOW_RISK": classification = "DEEP_EVIDENCE"
        reasons.extend(evidence or ["evidence_reasoning_path"])
    if task not in ("strategy", "formatting", "schema_transform", "metadata", "classification", "helper_text") or (not 0 < len(query) <= MAX_FAST_INPUT or not query.isascii()):
        if classification == "FAST_LOW_RISK": classification = "FORCE_PRIMARY"
        reasons.append("unbounded_or_unclassified_task")
    fast = classification == "FAST_LOW_RISK"
    return {"requested_path": requested_path, "model_selected": config.fast_model if fast else config.primary_model,
        "selected_model": config.fast_model if fast else config.primary_model,
        "model_role": "fast" if fast else "primary", "routing_class": classification,
        "routing_reasons": reasons or ["bounded_" + task], "escalated": bool(task and not fast),
        "escalation_reason": reasons[0] if task and not fast else None, "routing_fallback_reason": None}


def unique_json(pairs):
    value = {}
    for key, item in pairs:
        if key in value: raise ValueError("Duplicate contract key")
        value[key] = item
    return value


def generate_bounded(*, query, task: BoundedTask, messages, schema, signals=None,
                     requested_path="SYSTEM1", config=None, gateway_factory=None, contract=None):
    """At most one fast attempt, then primary. No tools, model confidence or downloads.

    Callers must authorize first and supply all deterministic risk facts. This is
    for internal bounded operations, not a public route or an evidence-answer API.
    """
    from app.core.config import settings
    from app.services.model_gateway import get_model_gateway
    from app.services.execution_observability import record_routing
    config = config or settings
    factory = gateway_factory or get_model_gateway
    # Bound the actual messages too, not just a caller's short routing description.
    content = "\n".join(message.content for message in messages)
    signals = signals or RiskSignals()
    if len(content) > MAX_FAST_INPUT:
        signals = signals.model_copy(update={"force_primary": True})
    if any(message.role == "tool" or message.tool_call_id for message in messages):
        signals = signals.model_copy(update={"high_risk_tools": True})
    user_content = "\n".join(message.content for message in messages if message.role != "system" and message.content != query)
    decision = select_model(query + ("\n" + user_content if user_content else ""), task=task, requested_path=requested_path,
                            signals=signals, config=config)
    model_calls = 0
    for attempt in range(2):
        record_routing(decision)
        try:
            gateway = factory(decision["model_role"])
            if not any(m.name == decision["model_selected"] for m in gateway.list_models()):
                raise ModelUnavailableError("Selected local model is not installed")
            model_calls += 1
            result = gateway.generate_structured(messages=messages, schema=schema, temperature=0,
                think=False, max_output_tokens=MAX_FAST_OUTPUT, repair_attempts=0,
                timeout_seconds=config.system1_timeout_seconds)
            if result.result.truncated or result.result.finish_reason != "stop" or result.result.tool_calls:
                raise StructuredOutputError("Bounded output was truncated or attempted a tool call")
            result.value = schema.model_validate(json.loads(result.result.text, object_pairs_hook=unique_json), strict=True)
            if contract is not None: contract(result.value)
            return result, {**decision, "routing_model_call_count": model_calls}
        except (ModelRuntimeError, ModelTimeoutError, ModelUnavailableError, StructuredOutputError,
                ToolCallProtocolError, ModelOutputTruncatedError, ValueError) as error:
            # Configuration errors are operator errors, never an invitation to switch models.
            if isinstance(error, ModelConfigurationError) or decision["model_role"] != "fast": raise
            reason = "fast_runtime_failure" if isinstance(error, (ModelRuntimeError, ModelTimeoutError, ModelUnavailableError)) else "fast_contract_failure"
            decision = {**decision, "model_selected": config.primary_model, "selected_model": config.primary_model, "model_role": "primary",
                "routing_class": "FORCE_PRIMARY", "routing_reasons": decision["routing_reasons"] + [reason],
                "escalated": True, "escalation_reason": reason, "routing_fallback_reason": reason}
    raise AssertionError("Routing attempts exhausted")
