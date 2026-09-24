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


def resolve_sources(session, chunk_ids, scope):
    store = get_qdrant()
    points = store.client.retrieve(store.collection, ids=[str(i) for i in chunk_ids], with_payload=True)
    indexed = {str(p.id): p for p in points}
    refs, snapshots = [], []
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


def create_candidate(session, payload, actor):
    authorize(session, actor)
    refs, snapshots = resolve_sources(session, payload.chunk_ids, payload.access_scope)
    parent = None
    if payload.supersedes_id:
        parent = session.get(VerifiedKnowledge, payload.supersedes_id)
        if parent is None or parent.access_scope != payload.access_scope:
            raise KnowledgeConflict("Unknown prior knowledge revision")
    now = datetime.now(timezone.utc)
    item = VerifiedKnowledge(id=uuid4(), title=payload.title, question=payload.question,
        match_key=canonical_hash(normalized(payload.question)), statement=payload.statement,
        evidence=refs, source_snapshot=snapshots, access_scope=payload.access_scope, status="CANDIDATE",
        revision=parent.revision + 1 if parent else 1, supersedes_id=parent.id if parent else None,
        created_by=actor.id, updated_at=now)
    item.content_hash = canonical_hash(binding(item))
    state = state_for(item, review=True)
    state["agent_result"]["knowledge_binding"] = binding(item)
    revision = create_revision(session, QueryRequest(query=item.question), state, requester_user_id=actor.id)
    item.approval_revision_id = revision.id
    session.add(item)
    session.flush()
    audit(session, item, "KNOWLEDGE_CANDIDATE_CREATED", actor)
    return item


def audit(session, item, event, actor=None, reason=None):
    append_event(session, event_type=event, actor_id=actor.id if actor else None,
        actor_kind="user" if actor else "system", action_revision_id=item.approval_revision_id,
        payload={"knowledge_id": str(item.id), "revision": item.revision,
                 "content_hash": item.content_hash, "status": item.status, "reason": reason})


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
        item.status = "STALE"
        item.updated_at = datetime.now(timezone.utc)
        audit(session, item, "KNOWLEDGE_STALE", reason=type(error).__name__)
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
    if operation == "verify":
        if item.status != "CANDIDATE":
            raise KnowledgeConflict("Only a current candidate may be verified")
        decision = apply_decision(session, revision_id=item.approval_revision_id, reviewer=actor,
                                  decision="approve", reviewer_comment=payload.comment)
        assert_release_allowed(session, item.approval_revision_id)
        item.status = "VERIFIED"
        item.verified_by = decision.approver_id
        item.verified_at = decision.decided_at
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
    audit(session, item, "KNOWLEDGE_" + item.status, actor)
    session.flush()
    return item


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
        "provenance": {"created_by": item.created_by, "mechanism": "existing_phase5_human_approval"}}


def import_candidate(document):
    from app.schemas.verified_knowledge import KnowledgeCandidate
    # Imported trust is never honored; source IDs are re-resolved on creation.
    if document.get("adapter_version") != "a1-v1":
        raise KnowledgeConflict("Unsupported adapter version")
    return KnowledgeCandidate(title=document["title"], question=document["question"],
        statement=document["statement"], chunk_ids=[r["chunk_id"] for r in document["evidence"]],
        access_scope=document["access_scope"])
