"""Human-provided records, immutable API, existing review/audit authority."""
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import select
from app.db.models import OperatorNote, IncidentReport, Equipment, EvidenceManifest, EvidenceManifestItem
from app.agents.evidence import OperationalRecordEvidence, make_evidence_id
from app.services.canonicalization import canonical_hash
from app.services.verified_knowledge import authorize, KnowledgeConflict
from app.services.governance import create_revision, get_governance_state
from app.services.audit import append_event
from app.schemas.query import QueryRequest


def equipment(session, tag):
    from app.services.equipment_tags import normalize_equipment_tag
    value = session.scalar(select(Equipment).where(Equipment.equipment_tag == normalize_equipment_tag(tag)))
    if value is None: raise KnowledgeConflict("Equipment identifier is not registered")
    return value


def snapshot(session, record_type, record_id):
    if record_type not in ("operator_note", "incident_report"): raise ValueError("Unsupported human report type")
    model = OperatorNote if record_type == "operator_note" else IncidentReport
    row = session.get(model, UUID(str(record_id)))
    if row is None: raise KnowledgeConflict("Human report unavailable")
    if record_type == "operator_note":
        if row.access_scope != "internal": raise KnowledgeConflict("Human report outside scope")
        data = {k: getattr(row, k) for k in ("author_id", "equipment_id", "unit", "text", "source_type", "access_scope")}
    else:
        data = {k: getattr(row, k) for k in ("equipment_id", "title", "description", "severity")}
    stamp = row.created_at
    if stamp.tzinfo is None: stamp = stamp.replace(tzinfo=timezone.utc)
    return {**{k: str(v) if isinstance(v, UUID) else v for k, v in data.items()},
            "record_id": str(row.id), "record_type": record_type, "created_at": stamp.isoformat()}


def evidence(session, row, record_type="operator_note"):
    digest = canonical_hash(snapshot(session, record_type, row.id))
    return OperationalRecordEvidence(evidence_id=make_evidence_id("operational_record", digest, str(row.id)),
        source_filename=record_type, source_sha256=digest, locator=f"{record_type} {row.id}",
        record_id=str(row.id), record_type=record_type)


def review_state(session, row):
    frozen = session.scalar(select(EvidenceManifestItem).join(EvidenceManifest).where(
        EvidenceManifest.action_revision_id == row.approval_revision_id,
        EvidenceManifestItem.source_identifier == f"operator_note:{row.id}"))
    if frozen is None or frozen.source_hash != canonical_hash(snapshot(session, "operator_note", row.id)):
        return "INVALID"
    status = get_governance_state(session, row.approval_revision_id) if row.approval_revision_id else "PENDING_REVIEW"
    return "HUMAN_REVIEWED" if status == "APPROVED" else status


def export(session, row):
    return {**snapshot(session, "operator_note", row.id), "review_state": review_state(session, row),
            "approval_revision_id": row.approval_revision_id, "trust": "HUMAN_REPORTED_NOT_VERIFIED_TECHNICAL_TRUTH"}


def create(session, payload, actor):
    authorize(session, actor)
    item = equipment(session, payload.equipment_tag)
    note = OperatorNote(id=uuid4(), author_id=actor.id, equipment_id=item.id, unit=payload.unit,
        text=payload.text, source_type="operator_report", access_scope="internal", created_at=datetime.now(timezone.utc))
    session.add(note); session.flush()
    ref = evidence(session, note)
    state = {"run_id": str(uuid4()), "query": "Review human-reported operator note",
        "route": "shift_handover", "evidence": [ref], "warnings": ["Review does not verify equipment state or authorize plant action."],
        "agent_result": {"schema": "OPERATOR_NOTE", "output": {"human_reported": payload.text,
            "author_id": str(actor.id), "human_approval_required": True}}, "step_records": []}
    revision = create_revision(session, QueryRequest(query=f"Review operator note {note.id}"), state, requester_user_id=actor.id)
    note.approval_revision_id = revision.id
    append_event(session, event_type="OPERATOR_NOTE_CREATED", actor_id=actor.id, actor_kind="user",
        action_revision_id=revision.id, payload={"note_id": str(note.id), "source_hash": ref.source_sha256})
    session.flush()
    return export(session, note)
