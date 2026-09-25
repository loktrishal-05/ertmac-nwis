"""As-drawn observations only. No geometry, field-state or authority inference."""
from app.agents.pid_evidence import OCR_LIMITATION


def observations(refs):
    result = []
    candidates = {}
    for ref in refs:
        if ref.kind != "pid_region": continue
        for item in ref.text_items:
            candidates.setdefault(item.text, set()).add(item.normalized_text)
    for ref in refs:
        if ref.kind != "pid_region": continue
        result.append({"evidence_id": ref.evidence_id, "document_id": ref.document_id,
            "document_version_id": ref.document_version_id, "drawing_revision": ref.revision,
            "locator": ref.locator, "region_id": ref.region_id, "source_sha256": ref.source_sha256,
            "raw_ocr": ref.combined_text, "confidence": ref.confidence, "status": ref.ocr_status,
            "labels": [{"raw_ocr": item.text, "normalized_candidate": item.normalized_text,
                "candidate_status": "UNRESOLVED" if ref.ocr_status == "ambiguous" or item.status == "ambiguous" or item.confidence < .6 or len(candidates[item.text]) > 1 else "UNVERIFIED",
                "conflicting_candidates": sorted(candidates[item.text]) if len(candidates[item.text]) > 1 else [],
                "human_verified_label": None, "model_interpretation": None, "category": item.category,
                "confidence": item.confidence, "bbox": list(item.bbox)} for item in ref.text_items],
            "title_block": "Not independently extracted; revision is supplied drawing metadata.", "limitations": [OCR_LIMITATION]})
    return result
