"""Deterministic RRF and conservative duplicate/revision handling."""
from datetime import date
from difflib import SequenceMatcher
import re


def fuse(dense, sparse, constant=60):
    candidates = {}
    for name, points in (("dense", dense), ("sparse", sparse)):
        seen = set()
        for rank, point in enumerate(points, 1):
            key = str(point.id)
            if key in seen:
                continue
            seen.add(key)
            item = candidates.setdefault(key, {"point": point, "dense_rank": None, "sparse_rank": None, "fusion_score": 0.0, "rerank_score": None})
            item[name + "_rank"] = rank
            item["fusion_score"] += 1 / (constant + rank)
    return sorted(candidates.values(), key=lambda c: (-c["fusion_score"], str(c["point"].id)))


def deduplicate(candidates, explicit_version=False):
    warnings, output = [], []
    # Prefer the latest known effective date only for the same logical document.
    # Without authority metadata, revision labels alone never establish currency.
    groups = {}
    for c in candidates:
        m = c["metadata"]
        groups.setdefault(str(m.document_id), {})[str(m.document_version_id)] = m
    selected = {}
    if not explicit_version:
        for doc, versions in groups.items():
            if len(versions) < 2:
                continue
            valid = [m for m in versions.values() if m.effective_date and m.effective_date <= date.today()]
            if len(valid) == len(versions):
                latest = max(m.effective_date for m in valid)
                current = [m for m in valid if m.effective_date == latest]
                if len(current) == 1:
                    selected[doc] = str(current[0].document_version_id)
                    warnings.append(f"Preferred effective revision {current[0].revision} for document {doc}; older candidate revisions omitted. Use document_version_id for historical evidence.")
                    continue
            warnings.append(f"Conflicting or uncertain current revisions for document {doc}; distinct evidence retained.")
    for item in candidates:
        m = item["metadata"]
        if str(m.document_id) in selected and str(m.document_version_id) != selected[str(m.document_id)]:
            continue
        text = " ".join(m.content.lower().split())
        duplicate = False
        for kept in output:
            other = kept["metadata"]
            if m.chunk_id == other.chunk_id:
                duplicate = True
                break
            same_version = m.document_version_id == other.document_version_id
            same_source = m.source_sha256 == other.source_sha256 and m.access_scope == other.access_scope
            same_ocr_location = False
            if m.ocr_derived and other.ocr_derived and m.source_image_uri == other.source_image_uri and m.page_start == other.page_start:
                for box in m.bounding_boxes:
                    for other_box in other.bounding_boxes:
                        a, b = box.coordinates, other_box.coordinates
                        overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
                        union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - overlap
                        same_ocr_location |= union > 0 and overlap / union >= 0.8
            if not (same_version or same_source) or (m.section_path != other.section_path and not same_ocr_location):
                continue
            other_text = " ".join(other.content.lower().split())
            # Different numerical/tag facts must survive even when prose is similar.
            facts = lambda s: re.findall(r"[a-z]*[-]?\d+[a-z0-9.%-]*|\b(?:not|no|never|prohibited|forbidden)\b", s)
            overlapping = m.page_start <= other.page_end and other.page_start <= m.page_end
            if text == other_text or (overlapping and facts(text) == facts(other_text) and SequenceMatcher(None, text, other_text, autojunk=False).ratio() >= 0.92):
                duplicate = True
                break
        if not duplicate:
            output.append(item)
    return output, warnings
