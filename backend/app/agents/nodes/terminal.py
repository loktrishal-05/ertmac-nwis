"""Terminal, non-agentic route outcomes: guardrail_refusal and clarification.
Both are S5 refusals built by the shared, non-model refuse() helper (see
app/agents/enforcement.py, D-006) from the router's own reasoning -- there is
no specialist agent for either route, per docs/phase4-decisions.md D-004."""
from app.agents.enforcement import refuse


def guardrail_refusal_node(state) -> dict:
    reason = "The request was blocked by a deterministic safety or capability guardrail."
    refusal = refuse(
        status="refused",
        reason=reason,
        safe_next_step="Rephrase the request without the unsupported or unsafe element, or contact a supervisor "
                       "for anything requiring an authorization this workbench does not grant.",
    )
    return {"agent_result": {"schema": "S5", "output": refusal.model_dump(mode="json")}}


def clarification_node(state) -> dict:
    reason = "The request needs a specific equipment tag, document reference, or operational question before it can be answered."
    refusal = refuse(
        status="clarification_required",
        reason=reason,
        missing_evidence=["clarifying details from the requester"],
        safe_next_step="Provide the missing identifier, time range, or equipment tag and ask again.",
    )
    return {"agent_result": {"schema": "S5", "output": refusal.model_dump(mode="json")}}
