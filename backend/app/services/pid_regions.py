"""Spatial text clustering only. Proximity is never connectivity evidence."""
from uuid import uuid5
from app.schemas.pid import OCRRegion


def merged_tags(items):
    keys = ("equipment_tags", "instrument_tags", "valve_tags", "line_numbers")
    return {key: sorted({tag for item in items for tag in item.identified_tags.get(key, [])}) for key in keys}


def bounds(items):
    return (min(i.bbox[0] for i in items), min(i.bbox[1] for i in items),
            max(i.bbox[2] for i in items), max(i.bbox[3] for i in items))


def group_regions(detections, version_id):
    """Greedy bounded text groups: no pipe, symbol, flow, or causal inference."""
    groups = []
    for item in sorted(detections, key=lambda d: (d.page, d.bbox[1], d.bbox[0])):
        match = None
        for group in reversed(groups):
            first = group[0]
            if item.page != first.page or item.source_image != first.source_image or len(group) >= 25:
                continue
            left, top, right, bottom = bounds(group)
            height = max(item.bbox[3] - item.bbox[1], first.bbox[3] - first.bbox[1])
            xgap = max(0, item.bbox[0] - right, left - item.bbox[2])
            ygap = max(0, item.bbox[1] - bottom, top - item.bbox[3])
            combined = bounds(group + [item])
            if xgap <= 3 * height and ygap <= 1.5 * height and combined[2] - combined[0] <= 20 * height and combined[3] - combined[1] <= 8 * height:
                match = group
                break
        if match is None:
            groups.append([item])
        else:
            match.append(item)
    regions = []
    for index, items in enumerate(groups):
        categories = {i.category for i in items}
        kind = "annotation_block"
        if "drawing_title" in categories or "revision" in categories:
            kind = "title_block"
        elif categories <= {"instrument_tag", "valve_tag"}:
            kind = "instrument_cluster"
        elif categories == {"equipment_tag"}:
            kind = "equipment_label"
        regions.append(OCRRegion(
            region_id=uuid5(version_id, f"region:{index}"), page=items[0].page,
            bbox=bounds(items), text_items=items, combined_text="\n".join(i.text for i in items),
            identified_tags=merged_tags(items), region_type=kind, source_image_uri=items[0].source_image,
        ))
    return regions
