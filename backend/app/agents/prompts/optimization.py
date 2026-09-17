"""Phase 4F: Process optimization agent prompts.

This agent reasons over process trends to suggest efficiency improvements,
always framed as proposals for human review, never as instructions or
directives. Every suggestion carries action_class='process_change' and
human_approval_required=true, and reuses the 4D authorisation-language
validator to ensure no output reads as an instruction.

Confounder acknowledgement is a prompt-level property: the agent must
surface competing explanations for correlated trends (e.g., both
differential pressure and flow rose together) rather than asserting
causation from correlation. This is prompt-enforced (a fixture test
validates it), not code-enforced like citation validity.

All arithmetic is deterministic Python: the agent proposes and phrases,
but the actual calculation of trend metrics (slope, percentage_change,
etc.) is already computed by Phase 3C's sensor_features system and
passed as evidence."""

from app.agents.prompts.shared import format_evidence_block

OPTIMIZATION_SYSTEM_PROMPT = (
    "You are an industrial process optimization analyst for a refinery operations workbench. "
    "Your role is to analyze trends in process sensor data and operational records, then propose "
    "efficiency improvements or parameter adjustments.\n\n"
    "CRITICAL CONSTRAINTS:\n"
    "- Every suggestion you make is a PROPOSAL for human review and approval, never an instruction "
    "or directive. You do NOT authorize action; you propose it.\n"
    "- Arithmetic is already done for you (slope, percentage_change, rate_of_change, and other "
    "trend metrics are pre-computed). You describe what the trends show and what they might mean; "
    "you do NOT calculate new numbers yourself.\n"
    "- When two variables move together (e.g., differential pressure rises AND flow increases in the "
    "same window), acknowledge both trends and surface the possibility that one explains the other, "
    "rather than asserting a single cause.\n"
    "- Every proposed set-point change or valve-position adjustment must be phrased as a proposal "
    "for qualified review, not a directive.\n"
    "- You cite only the evidence that was actually provided to you this turn.\n\n"
    "Output the corrected JSON object only; do not include explanatory text outside the JSON."
)


def build_optimization_user_message(query: str, equipment_tag: str, evidence_blocks: list[str]) -> str:
    """Builds the user message for the optimization agent, passing sensor trends and
    related evidence as delimited blocks."""
    evidence_section = "\n\n".join(evidence_blocks) if evidence_blocks else "(No evidence gathered)"
    return (
        f"Query: {query}\n\n"
        f"Equipment tag in scope: {equipment_tag}\n\n"
        f"Evidence (trends, readings, and operational history):\n\n{evidence_section}\n\n"
        "Your task:\n"
        "1. Analyze these trends and historical records.\n"
        "2. Identify any correlations, patterns, or anomalies.\n"
        "3. When you observe co-movement in two variables, explicitly surface the possibility "
        "that one explains the other -- do not hide competing explanations.\n"
        "4. Propose any process improvements, parameter adjustments, or operational changes "
        "that might improve efficiency or reliability.\n"
        "5. Every proposal must be framed as a suggestion for human review and approval.\n"
        "6. Cite evidence for your observations and recommendations.\n\n"
        "Emit a JSON object with the schema: "
        "{\n"
        '  "summary": "...",\n'
        '  "evidence_basis": ["..."],\n'
        '  "proposed_actions": [\n'
        '    {\n'
        '      "action": "...",\n'
        '      "action_class": "process_change",\n'
        '      "approval_status": "required"\n'
        '    }\n'
        '  ],\n'
        '  "citations": [...],\n'
        '  "confidence": 0.0 to 1.0,\n'
        '  "warnings": [...],\n'
        '  "human_approval_required": true\n'
        "}"
    )
