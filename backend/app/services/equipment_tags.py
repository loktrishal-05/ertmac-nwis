"""Conservative equipment-tag normalization and find-or-create, reused from OCR/document tagging."""
import re
from uuid import uuid4

from sqlalchemy import select

from app.db.models.equipment import Equipment
from app.services.pid_identifiers import normalize_identifier

# Same letter-prefix vocabulary as app.services.tags.DEFAULT_PATTERNS equipment_tags.
BARE_TAG = re.compile(r"^(P|V|E|C|T|R|K|M)(\d{2,5})([A-Z]?)$")


def normalize_equipment_tag(raw: str) -> str:
    """Uppercase/dash-unify via normalize_identifier, then conservatively insert a
    missing dash only when the result exactly matches a known bare tag shape
    (e.g. P204 -> P-204). Ambiguous spellings are left untouched, never merged."""
    value = normalize_identifier(raw)
    match = BARE_TAG.fullmatch(value)
    if match:
        prefix, digits, suffix = match.groups()
        value = f"{prefix}-{digits}{suffix}"
    return value


def find_or_create_equipment(session, raw_tag: str) -> Equipment:
    tag = normalize_equipment_tag(raw_tag)
    if not tag:
        raise ValueError("equipment_tag is required")
    equipment = session.scalar(select(Equipment).where(Equipment.equipment_tag == tag))
    if equipment is None:
        equipment = Equipment(id=uuid4(), equipment_tag=tag, name=tag, equipment_type="unknown", location=None)
        session.add(equipment)
        session.flush()
    return equipment
