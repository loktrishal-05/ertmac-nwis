"""Evidence-block formatting shared by every specialist prompt (4C-4F).
Moved here out of prompts/knowledge.py (which re-exports it for existing
importers) once a second specialist (4D) needed the identical framing:
retrieved/queried content is always presented as a delimited, labelled,
explicitly-quoted block, never inlined as free text -- see
prompts/knowledge.py's own docstring for the prompt-injection rationale."""


def format_evidence_block(evidence_id: str, locator: str, text: str) -> str:
    return f'<evidence id="{evidence_id}" locator="{locator}">\n{text}\n</evidence>'
