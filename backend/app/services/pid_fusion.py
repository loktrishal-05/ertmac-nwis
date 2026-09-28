"""Deterministic candidate fusion; imagery cannot establish operational facts."""
from sqlalchemy import select
from app.db.models import Equipment, VerifiedKnowledge
from app.schemas.pid import RegionFusion
from app.services.equipment_tags import normalize_equipment_tag

LIMITATION = ("Imagery and OCR cannot prove topology, connectivity, flow direction, valve open/closed state, "
              "isolation, LOTO, permit state, startup/shutdown readiness, safe-to-operate or process readiness. "
              "Verified identity means a documented tag only, never symbol association or current field state.")


def registry_evidence(session, tag):
    """Inventory rows may be auto-created. Require current reviewed definition for authority."""
    if session is None or not tag:
        return None
    asset = session.scalar(select(Equipment).where(Equipment.equipment_tag == tag))
    if asset is None:
        return {"status": "missing", "tag": tag}
    result = {"status": "matched", "tag": tag, "equipment_id": str(asset.id)}
    from app.services.verified_knowledge import normalized, refresh
    from app.services.canonicalization import canonical_hash
    question = f"what is the documented definition of {tag}?"
    records = session.scalars(select(VerifiedKnowledge).where(
        VerifiedKnowledge.match_key == canonical_hash(normalized(question)),
        VerifiedKnowledge.access_scope == "internal", VerifiedKnowledge.status == "VERIFIED")).all()
    valid = [item for item in records if refresh(session, item)]
    if len(valid) == 1:
        result.update(status="verified", knowledge_id=str(valid[0].id),
                      approval_revision_id=str(valid[0].approval_revision_id), sources=valid[0].source_snapshot)
    elif len(valid) > 1:
        result["status"] = "conflicting"
    return result


def overlaps(a, b):
    return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])


def fuse(item=None, visuals=(), registry=None):
    tag = normalize_equipment_tag(item.normalized_text) if item else None
    visual_tags = sorted({v.tag for v in visuals if v.tag})
    candidate = tag or (visual_tags[0] if len(visual_tags) == 1 else None)
    origins = (["OCR"] if item else []) + (["VISUAL_MODEL"] if visuals else [])
    reasons, provenance = [], []
    status = "CANDIDATE" if item else ("UNVERIFIED" if visuals else "UNKNOWN")
    if item and (item.confidence < .6 or item.status == "ambiguous"):
        reasons.append("low_or_ambiguous_ocr")
    if any(v.confidence < .6 or v.uncertainty != "unverified_visual_observation" for v in visuals):
        reasons.append("visual_ambiguity")
    if len(visual_tags) > 1 or (tag and visual_tags and any(v != tag for v in visual_tags)):
        reasons.append("ocr_visual_disagreement_or_ambiguous_identity")
        status = "CONFLICTING"
    if registry:
        origins.append("REGISTRY")
        provenance.append(registry)
        if registry["status"] == "conflicting" or registry.get("tag") != candidate or (item and registry["status"] == "missing"):
            status = "CONFLICTING"
            reasons.append("registry_mismatch")
        elif registry["status"] == "verified" and item and not reasons:
            status = "VERIFIED"
            origins.append("HUMAN_VERIFIED")
    if status != "VERIFIED":
        reasons.append("identity_requires_human_review")
    return RegionFusion(equipment_candidate=candidate, raw_ocr_text=item.text if item else None,
        normalized_text=tag, ocr_confidence=item.confidence if item else None,
        visual_candidate=visual_tags[0] if len(visual_tags) == 1 else None,
        visual_confidence=visuals[0].confidence if len(visuals) == 1 else None,
        registry_status=status, evidence_origin=origins, provenance=provenance,
        limitations=[LIMITATION] + reasons, review_required=bool(reasons))


def region_fusion(region, session=None):
    result, used = [], set()
    for item in region.text_items:
        if item.category not in {"equipment_tag", "instrument_tag", "valve_tag"}:
            continue
        # A region shared by multiple OCR labels can make a symbol association ambiguous.
        nearby = [v for v in region.visual_candidates if overlaps(item.bbox, v.bbox)]
        used.update(id(v) for v in nearby)
        result.append(fuse(item, nearby, registry_evidence(session, normalize_equipment_tag(item.normalized_text))))
    for visual in region.visual_candidates:
        if id(visual) not in used:
            result.append(fuse(visuals=[visual], registry=registry_evidence(session, visual.tag)))
    return result
