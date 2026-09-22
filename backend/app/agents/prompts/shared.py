"""Evidence-block formatting shared by every specialist prompt (4C-4F).
Moved here out of prompts/knowledge.py (which re-exports it for existing
importers) once a second specialist (4D) needed the identical framing:
retrieved/queried content is always presented as a delimited, labelled,
explicitly-quoted block, never inlined as free text -- see
prompts/knowledge.py's own docstring for the prompt-injection rationale."""
from html import escape
import json


def format_evidence_block(evidence_id: str, locator: str, text: str) -> str:
    return f'<evidence id="{escape(str(evidence_id), quote=True)}" locator="{escape(str(locator), quote=True)}">\n{text}\n</evidence>'


def format_evidence_ref(ref) -> str:
    metadata = [f"source_filename={ref.source_filename}", f"source_sha256={ref.source_sha256}"]
    for name in ("source_uri", "revision", "region_id", "source_image_uri", "ocr_confidence", "ocr_status"):
        value = getattr(ref, name, None)
        if value is not None:
            metadata.append(f"{name}={value}")
    if getattr(ref, "ocr_derived", False):
        metadata.insert(0, "THIS IS OCR-DERIVED EVIDENCE; do not infer topology, connectivity, flow direction, valve state, or isolation")
    text = getattr(ref, "quote", None) or getattr(ref, "combined_text", None) or ""
    if getattr(ref, 'text_items', None):
        text += '\nRaw OCR and separate normalized candidates: ' + json.dumps(
            [item.model_dump(mode='json') for item in ref.text_items], ensure_ascii=False)
    return format_evidence_block(ref.evidence_id, ref.locator, "[" + "; ".join(metadata) + "]\n" + text)
