"""Exact-match, human-verified document knowledge; no model or write tool authority."""
import hashlib
import json
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import select
from app.agents.evidence import document_chunk_evidence
from app.core.config import settings
from app.db.models import ActionRevision, Document, DocumentVersion, User, VerifiedKnowledge
from app.schemas.agent_outputs import GroundedAnswer
from app.schemas.knowledge import ChunkMetadata
from app.schemas.query import QueryRequest
from app.services.approval import apply_decision, DecisionNotAllowed
from app.services.audit import append_event
from app.services.canonicalization import canonical_hash
from app.services.governance import create_revision, evaluate_governance, assert_release_allowed, assert_still_approved_under_lock, ReleaseNotAllowed
from app.services.preflight import run_preflight
from app.services.qdrant_service import get_qdrant

class KnowledgeConflict(ValueError):
    pass

class SourceChanged(KnowledgeConflict):
    pass


def normalized(question):
    # Preserve punctuation, digits and identifiers; no semantic matching.
    return " ".join(question.casefold().split())


def authorize(session, user, review=False):
    with session.no_autoflush:
        role = session.scalar(select(User.role).where(User.id == getattr(user, "id", None)))
    if role not in (("reviewer", "admin") if review else ("requester", "reviewer", "admin")):
        raise DecisionNotAllowed("Authenticated authorized human account required")
    return role  # Always the stored role, never one supplied with the request.


def resolve_sources(session, chunk_ids, scope, with_scope=False):
    store = get_qdrant()
    points = store.client.retrieve(store.collection, ids=[str(i) for i in chunk_ids], with_payload=True)
    indexed = {str(p.id): p for p in points}
    refs, snapshots = [], []
    asset = {"equipment_tags": set(), "unit_ids": set(), "facility_ids": set(), "document_ids": set()}
    if len(set(chunk_ids)) != len(chunk_ids):
        raise SourceChanged("Duplicate source identifiers")
    for key in chunk_ids:
        point = indexed.get(str(key))
        if point is None:
            raise SourceChanged("Source chunk no longer available")
        chunk = ChunkMetadata.model_validate(point.payload)
        version = session.scalars(select(DocumentVersion).where(DocumentVersion.id == chunk.document_version_id)
                                  .execution_options(populate_existing=True)).one_or_none()
        doc = session.scalars(select(Document).where(Document.id == chunk.document_id)
                              .execution_options(populate_existing=True)).one_or_none()
        if (chunk.chunk_id != key or chunk.ocr_derived or scope != "internal" or chunk.access_scope != scope
                or version is None or doc is None or version.created_at is None or version.document_id != doc.id
                or doc.classification != scope or version.status != "indexed" or doc.ingestion_status != "indexed"
                or version.source_sha256 != chunk.source_sha256 or doc.checksum != chunk.source_sha256
                or version.ingestion_metadata.get("access_scope") != scope
                or version.ingestion_metadata.get("revision") != chunk.revision):
            raise SourceChanged("Source revision, scope, OCR or lifecycle is not eligible")
        # Any newer revision (even one still processing) invalidates trust in the old one.
        if session.scalar(select(DocumentVersion.id).where(DocumentVersion.document_id == doc.id,
                DocumentVersion.id != version.id, DocumentVersion.created_at >= version.created_at).limit(1)):
            raise SourceChanged("Newer source revision exists")
        path = Path(doc.source_path).resolve()
        if not path.is_relative_to(settings.data_root.resolve()) or not path.is_file():
            raise SourceChanged("Local source unavailable")
        if hashlib.sha256(path.read_bytes()).hexdigest() != chunk.source_sha256:
            raise SourceChanged("Local source content changed")
        ref = document_chunk_evidence(chunk_id=key, document_id=doc.id, document_version_id=version.id,
            source_filename=chunk.source_filename, source_sha256=chunk.source_sha256,
            section_path=chunk.section_path, page_start=chunk.page_start, page_end=chunk.page_end,
            bounding_boxes=[b.model_dump(mode="json") for b in chunk.bounding_boxes], quote=chunk.content,
            source_uri=chunk.source_uri, revision=chunk.revision)
        refs.append(ref.model_dump(mode="json"))
        snapshots.append({"document_id": str(doc.id), "document_version_id": str(version.id),
            "revision": chunk.revision, "source_sha256": chunk.source_sha256,
            "chunk_id": str(key), "chunk_hash": canonical_hash(chunk.model_dump(mode="json")),
            "version_metadata_hash": canonical_hash(version.ingestion_metadata)})
        asset["equipment_tags"].update(chunk.equipment_tags)
        asset["unit_ids"].update([str(chunk.unit_id)] if chunk.unit_id else [])
        asset["facility_ids"].update([str(chunk.facility_id)] if chunk.facility_id else [])
        asset["document_ids"].add(str(doc.id))
    if with_scope:
        return refs, snapshots, {key: sorted(value) for key, value in asset.items()}
    return refs, snapshots


def binding(item):
    return {"knowledge_id": str(item.id), "title": item.title, "question": item.question,
            "statement": item.statement, "evidence": item.evidence, "sources": item.source_snapshot,
            "access_scope": item.access_scope, "revision": item.revision,
            "supersedes_id": str(item.supersedes_id) if item.supersedes_id else None}


def state_for(item, review=False):
    output = GroundedAnswer(answer=item.statement, observations=[], hypotheses=[],
        citations=[{"evidence_id": r["evidence_id"], "locator": r["locator"], "claim": item.statement} for r in item.evidence],
        confidence=1.0, limitations=["Human-reviewed document statement; not proof of current plant conditions."],
        human_approval_required=review).model_dump(mode="json")
    return {"run_id": str(uuid4()), "query": item.question, "route": "knowledge",
            "agent_result": {"schema": "S1", "output": output}, "evidence": item.evidence,
            "human_approval_required": review, "warnings": [], "step_records": []}


def eligible(question, statement):
    # Static documented-fact questions only. No current-condition or action advice.
    if not re.fullmatch(r"what is the documented (?:[a-z-]+ ){0,6}(?:limit|threshold|rating|unit|definition) (?:for|of) [a-z][a-z0-9-]{1,40}\??", normalized(question)):
        return False
    if re.search(r"\b(current|now|safe|isolation|valve|permit|shutdown|start|stop|action|should|recommend|emergency|leak|fire|gas|evacuate|inspect|repair|operate|perform|proceed|must|should)\b", question + " " + statement, re.I):
        return False
    if run_preflight(question, "internal").decision != "ALLOW" or (statement and run_preflight(statement, "internal").decision != "ALLOW"):
        return False
    return evaluate_governance(QueryRequest(query=question), {
        "agent_result": {"schema": "S1", "output": {"answer": statement}}}) == "INFORMATIONAL"


def check_origin(session, origin, reference):
    """Origins are provenance labels; a referenced record must exist, but grants no trust."""
    from app.db.models import KnowledgeGap, OperatorNote
    if origin in ("knowledge_gap", "operator_note") and not reference:
        raise KnowledgeConflict("This origin requires a reference")
    if origin == "knowledge_gap":
        gap = session.get(KnowledgeGap, reference)
        if gap is None or gap.access_scope != "internal" or gap.status in ("RESOLVED", "DISMISSED"):
            raise KnowledgeConflict("Referenced knowledge gap is not open")
    if origin == "operator_note":
        try:
            note = session.get(OperatorNote, UUID(reference))
        except ValueError:
            note = None
        if note is None or note.access_scope != "internal":
            raise KnowledgeConflict("Referenced operator note unavailable")


def create_candidate(session, payload, actor):
    authorize(session, actor)
    check_origin(session, payload.origin, payload.origin_reference)
    # OCR-derived (P&ID) chunks are rejected here, so visual candidates can never become sources.
    refs, snapshots, asset_scope = resolve_sources(session, payload.chunk_ids, payload.access_scope, with_scope=True)
    parent = None
    if payload.supersedes_id:
        parent = session.get(VerifiedKnowledge, payload.supersedes_id)
        if parent is None or parent.access_scope != payload.access_scope:
            raise KnowledgeConflict("Unknown prior knowledge revision")
        # Re-verification continues VERIFIED/STALE knowledge; REVOKED is terminal.
        if parent.status not in ("VERIFIED", "STALE"):
            raise KnowledgeConflict("Only verified or stale knowledge can be re-verified")
    now = datetime.now(timezone.utc)
    item = VerifiedKnowledge(id=uuid4(), title=payload.title, question=payload.question,
        match_key=canonical_hash(normalized(payload.question)), statement=payload.statement,
        evidence=refs, source_snapshot=snapshots, access_scope=payload.access_scope, status="CANDIDATE",
        revision=parent.revision + 1 if parent else 1, supersedes_id=parent.id if parent else None,
        created_by=actor.id, updated_at=now, origin=payload.origin,
        origin_reference=payload.origin_reference, asset_scope=asset_scope)
    item.content_hash = canonical_hash(binding(item))
    state = state_for(item, review=True)
    state["agent_result"]["knowledge_binding"] = binding(item)
    revision = create_revision(session, QueryRequest(query=item.question), state, requester_user_id=actor.id)
    item.approval_revision_id = revision.id
    session.add(item)
    session.flush()
    audit(session, item, "KNOWLEDGE_CANDIDATE_CREATED", actor, reason=item.origin)
    return item


def audit(session, item, event, actor=None, reason=None, previous=None):
    """One tamper-evident record per transition: who (stored role), what, why, and against which sources."""
    append_event(session, event_type=event, actor_id=actor.id if actor else None,
        actor_kind="user" if actor else "system", action_revision_id=item.approval_revision_id,
        payload={"knowledge_id": str(item.id), "revision": item.revision,
                 "content_hash": item.content_hash, "status": item.status, "reason": reason,
                 "previous_status": previous, "actor_role": authorize(session, actor) if actor else "system",
                 "origin": item.origin, "origin_reference": item.origin_reference, "asset_scope": item.asset_scope,
                 "supersedes_id": str(item.supersedes_id) if item.supersedes_id else None,
                 "sources": [{k: s.get(k) for k in ("document_id", "document_version_id", "revision", "source_sha256")}
                             for s in item.source_snapshot]})


def refresh(session, item):
    if item.status not in ("CANDIDATE", "VERIFIED"):
        return False
    try:
        revision = session.get(ActionRevision, item.approval_revision_id)
        signed = json.loads(revision.canonical_proposal)["payload"]["agent_result"]["knowledge_binding"]
        if canonical_hash(binding(item)) != item.content_hash or signed != binding(item):
            raise SourceChanged("Knowledge differs from immutable reviewed proposal")
        refs, snapshots = resolve_sources(session, [UUID(r["chunk_id"]) for r in item.evidence], item.access_scope)
        if refs != item.evidence or snapshots != item.source_snapshot:
            raise SourceChanged("Evidence revision or content changed")
        if item.status == "VERIFIED":
            assert_release_allowed(session, item.approval_revision_id)
        return True
    except (SourceChanged, ReleaseNotAllowed, ValueError, KeyError, AttributeError) as error:
        previous, item.status = item.status, "STALE"
        item.updated_at = datetime.now(timezone.utc)
        audit(session, item, "KNOWLEDGE_STALE", reason=type(error).__name__, previous=previous)
        session.flush()
        return False


def inspect_item(session, knowledge_id, actor):
    authorize(session, actor)
    item = session.scalars(select(VerifiedKnowledge).where(VerifiedKnowledge.id == knowledge_id)
                           .with_for_update().execution_options(populate_existing=True)).one_or_none()
    if item is None or item.access_scope != "internal":
        raise KnowledgeConflict("Knowledge not found in authorized scope")
    refresh(session, item)
    return item


def decide(session, knowledge_id, payload, actor, operation):
    authorize(session, actor, review=True)
    item = inspect_item(session, knowledge_id, actor)
    if item.content_hash != payload.expected_content_hash:
        raise KnowledgeConflict("Review content hash mismatch")
    previous = item.status
    if operation == "verify":
        if item.status != "CANDIDATE":
            raise KnowledgeConflict("Only a current candidate may be verified")
        decision = apply_decision(session, revision_id=item.approval_revision_id, reviewer=actor,
                                  decision="approve", reviewer_comment=payload.comment)
        assert_release_allowed(session, item.approval_revision_id)
        item.status = "VERIFIED"
        item.verified_by = decision.approver_id
        item.verified_at = decision.decided_at
        parent = session.get(VerifiedKnowledge, item.supersedes_id) if item.supersedes_id else None
        if parent is not None and parent.status == "VERIFIED":
            # Re-verification supersedes; the prior row and its verification remain as history.
            parent.status, parent.updated_at = "STALE", datetime.now(timezone.utc)
            audit(session, parent, "KNOWLEDGE_STALE", actor, reason="superseded_by:" + str(item.id), previous="VERIFIED")
    elif operation in ("stale", "revoke"):
        if item.status == "REVOKED":
            raise KnowledgeConflict("Knowledge already revoked")
        if operation == "revoke":
            from app.services.governance import get_governance_state
            ledger = get_governance_state(session, item.approval_revision_id)
            if ledger in ("APPROVED", "PENDING_REVIEW"):
                apply_decision(session, revision_id=item.approval_revision_id, reviewer=actor,
                    decision="revoke" if ledger == "APPROVED" else "reject", reviewer_comment=payload.comment)
        item.status = "REVOKED" if operation == "revoke" else "STALE"
    else:
        raise KnowledgeConflict("Unknown lifecycle operation")
    item.updated_at = datetime.now(timezone.utc)
    audit(session, item, "KNOWLEDGE_" + item.status, actor, reason=payload.comment, previous=previous)
    session.flush()
    return item


def revalidate(session, actor, document_id=None):
    """Authorized sweep: re-check current sources now instead of on next read.

    Reads already fail closed through refresh(); this makes invalidation visible
    in the registry and audit chain right after a source revision or mutation."""
    authorize(session, actor, review=True)
    items = session.scalars(select(VerifiedKnowledge).where(VerifiedKnowledge.status.in_(("CANDIDATE", "VERIFIED")),
        VerifiedKnowledge.access_scope == "internal").with_for_update().execution_options(populate_existing=True)).all()
    # ponytail: linear scan over live knowledge; add a source index if the registry grows large.
    if document_id:
        items = [i for i in items if any(s.get("document_id") == str(document_id) for s in i.source_snapshot)]
    changed = [i for i in items if not refresh(session, i)]
    session.flush()
    return changed


def history(session, knowledge_id, actor):
    """Revision lineage plus every audit event bound to those governed revisions, in chain order."""
    from app.db.models import AuditEvent
    authorize(session, actor, review=True)  # Audit events carry the /audit/log visibility (reviewer/admin).
    item = inspect_item(session, knowledge_id, actor)
    lineage, cursor, seen = [], item, set()
    while cursor is not None and cursor.id not in seen and len(lineage) < 100:
        seen.add(cursor.id)
        lineage.insert(0, cursor)
        cursor = session.get(VerifiedKnowledge, cursor.supersedes_id) if cursor.supersedes_id else None
    while len(lineage) < 100:  # Bounded lineage; detailed events also remain available through /audit/log.
        successor = session.scalar(select(VerifiedKnowledge).where(VerifiedKnowledge.supersedes_id == lineage[-1].id)
                                   .order_by(VerifiedKnowledge.created_at, VerifiedKnowledge.id).limit(1))
        if successor is None or successor.id in seen:
            break
        seen.add(successor.id)
        lineage.append(successor)
    events = session.scalars(select(AuditEvent).where(AuditEvent.action_revision_id.in_(
        [i.approval_revision_id for i in lineage])).order_by(AuditEvent.sequence_number).limit(501)).all()
    return {"knowledge_id": str(item.id), "lineage": [export_item(i) for i in lineage],
            "as_of": datetime.now(timezone.utc), "lineage_limit": 100, "events_limit": 500,
            "truncated": len(lineage) == 100 or len(events) > 500,
            "events": [{"sequence_number": e.sequence_number, "event_type": e.event_type, "occurred_at": e.occurred_at,
                        "actor_id": e.actor_id, "actor_kind": e.actor_kind, "action_revision_id": e.action_revision_id,
                        "payload": e.payload, "event_hash": e.event_hash} for e in events[:500]],
            "integrity": "Tamper-evident audit chain; verify with the audit chain verifier, not tamper-proof."}


def lookup(session, request, actor):
    started = time.perf_counter()
    meta = {"path": "EXISTING_AGENTIC_PATH", "fallback_reason": "no_exact_verified_match"}
    if actor is None or request.access_scope != "internal":
        meta["fallback_reason"] = "authentication_or_scope"
        return None, meta
    authorize(session, actor)
    if not eligible(request.query, ""):
        meta["fallback_reason"] = "not_static_informational"
        return None, meta
    candidates = session.scalars(select(VerifiedKnowledge).where(
        VerifiedKnowledge.match_key == canonical_hash(normalized(request.query)),
        VerifiedKnowledge.access_scope == request.access_scope, VerifiedKnowledge.status == "VERIFIED")
        .with_for_update().execution_options(populate_existing=True)).all()
    valid = []
    for item in candidates:
        if refresh(session, item) and eligible(request.query, item.statement):
            valid.append(item)
    if len(valid) != 1:
        meta["fallback_reason"] = "ambiguous_match" if len(valid) > 1 else "no_current_verified_match"
        session.commit()  # Persist deterministic invalidation and its audit together.
        return None, meta
    item = valid[0]
    state = state_for(item)
    # Governance still runs at the common /query boundary. Verification is not plant approval.
    meta = {"path": "VERIFIED_FAST_PATH", "knowledge_id": str(item.id), "revision": item.revision,
            "verification_state": item.status, "verified_at": item.verified_at.isoformat(),
            "approval_revision_id": str(item.approval_revision_id),
            "sources": item.source_snapshot, "latency_ms": (time.perf_counter()-started)*1000}
    assert_still_approved_under_lock(session, item.approval_revision_id)
    audit(session, item, "VERIFIED_KNOWLEDGE_SERVED", actor)
    session.commit()
    return state, meta


def export_item(item):
    # Application-owned mapping, not a claim of certified external conformance.
    return {"representation": "OKF-compatible adapter/representation layer", "adapter_version": "a1-v1",
        **binding(item), "content_hash": item.content_hash, "lifecycle_state": item.status,
        "trust": {"verified_at": item.verified_at, "verified_by": item.verified_by,
                  "approval_revision_id": item.approval_revision_id},
        "timestamps": {"created_at": item.created_at, "updated_at": item.updated_at},
        "provenance": {"created_by": item.created_by, "mechanism": "existing_phase5_human_approval",
                       "origin": item.origin, "origin_reference": item.origin_reference},
        "asset_scope": item.asset_scope}


def import_candidate(document):
    from app.schemas.verified_knowledge import KnowledgeCandidate
    # Imported trust is never honored; source IDs are re-resolved on creation.
    if document.get("adapter_version") != "a1-v1":
        raise KnowledgeConflict("Unsupported adapter version")
    return KnowledgeCandidate(title=document["title"], question=document["question"],
        statement=document["statement"], chunk_ids=[r["chunk_id"] for r in document["evidence"]],
        access_scope=document["access_scope"])
