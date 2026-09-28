"""Deterministic, deduplicated gaps; no confidence or autonomous resolution."""
from app.services.canonicalization import canonical_hash


def detect(subject, sufficiency=None, requests=(), evidence=()):
    supplied = list(requests)
    if sufficiency:
        supplied += [{"gap_type": "missing_" + x, "required_evidence": x} for x in sufficiency.get("missing_categories", [])]
        supplied += [{"gap_type": x, "required_evidence": "current cited source"} for x in sufficiency.get("issues", [])]
    for ref in evidence:
        data = ref.model_dump(mode="json") if hasattr(ref, "model_dump") else ref
        if data.get("kind") == "pid_region" and not data.get("revision"):
            supplied.append({"gap_type": "missing_pid_revision", "required_evidence": "identified current drawing revision",
                             "related_evidence": [data["evidence_id"]]})
        if data.get("ocr_status") == "ambiguous" or any(x.get("status") == "ambiguous" for x in data.get("text_items", [])):
            supplied.append({"gap_type": "ocr_ambiguity", "required_evidence": "readable region and independent human field verification",
                             "related_evidence": [data["evidence_id"]]})
    from app.services.evidence_sufficiency import refs_as_models
    from app.services.visual_intelligence import observations
    for region in observations(refs_as_models(evidence)):
        if any(f["review_required"] for f in region.get("fusion", [])):
            supplied.append({"gap_type": "pid_identity_review", "required_evidence": "current authoritative registry definition and human reconciliation",
                             "related_evidence": [region["evidence_id"]]})
        if any(label["conflicting_candidates"] for label in region["labels"]):
            supplied.append({"gap_type": "conflicting_evidence", "required_evidence": "human reconciliation of conflicting OCR candidates",
                             "related_evidence": [region["evidence_id"]]})
    result = {}
    for value in supplied:
        kind = value["gap_type"]
        key = canonical_hash({"subject": subject, "gap_type": kind})
        if key not in result:
            result[key] = {"gap_id": key, "gap_type": kind, "subject": subject,
                "required_evidence": value.get("required_evidence", kind), "reason": value.get("reason", "Required evidence was not established."),
                "category": "EVIDENCE", "severity": "HIGH" if any(x in kind for x in ("sensor", "rule", "threshold", "conflict", "stale", "pid")) else "REVIEW",
                "related_evidence": [], "recommended_information_request": "Provide and review " + value.get("required_evidence", kind),
                "status": "OPEN"}
        result[key]["related_evidence"] = sorted(set(result[key]["related_evidence"] + value.get("related_evidence", [])))
    return list(result.values())
