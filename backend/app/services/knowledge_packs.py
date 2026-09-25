"""CAG means bounded approved context, not runtime KV-cache reuse."""
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from app.db.models import KnowledgePack, VerifiedKnowledge
from app.schemas.verified_knowledge import KnowledgeCandidate
from app.services import verified_knowledge as v
from app.services.governance import assert_still_approved_under_lock

class PackCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1, max_length=300)
    question: str = Field(min_length=1, max_length=500)
    knowledge_ids: list[UUID] = Field(min_length=1, max_length=5)


def review_question(pack):
    return "Context pack review: " + json.dumps({"pack_id": str(pack.id), "name": pack.name,
        "description": pack.description, "question": pack.question, "members": pack.members}, sort_keys=True)


def create(session, payload, actor):
    v.authorize(session, actor)
    if len(set(payload.knowledge_ids)) != len(payload.knowledge_ids):
        raise v.KnowledgeConflict("Duplicate pack members")
    items = [v.inspect_item(session, i, actor) for i in payload.knowledge_ids]
    if any(i.status != "VERIFIED" or not v.eligible(payload.question, i.statement) for i in items):
        raise v.KnowledgeConflict("Pack requires current verified informational internal knowledge")
    evidence = list({r["chunk_id"]: r for i in items for r in i.evidence}.values())
    statement = "\n\n".join(i.statement for i in items)
    if len(evidence) > 10 or len(json.dumps(evidence)) + len(statement) > 16000 or len(statement) > 6000:
        raise v.KnowledgeConflict("Pack exceeds bounded context size")
    pack = KnowledgePack(id=uuid4(), name=payload.name, description=payload.description,
        question=payload.question, match_key=v.canonical_hash(v.normalized(payload.question)),
        members=[{"knowledge_id": str(i.id), "content_hash": i.content_hash, "revision": i.revision} for i in items])
    if len(review_question(pack)) > 2000:
        raise v.KnowledgeConflict("Pack review metadata exceeds bound")
    aggregate = v.create_candidate(session, KnowledgeCandidate(title="Context pack: " + pack.name,
        question=review_question(pack), statement=statement, chunk_ids=[r["chunk_id"] for r in evidence]), actor)
    pack.knowledge_id = aggregate.id
    session.add(pack); session.flush()
    return pack


def inspect(session, pack_id, actor):
    v.authorize(session, actor)
    pack = session.scalars(select(KnowledgePack).where(KnowledgePack.id == pack_id)
        .with_for_update().execution_options(populate_existing=True)).one_or_none()
    if pack is None:
        raise v.KnowledgeConflict("Pack not found")
    aggregate = v.inspect_item(session, pack.knowledge_id, actor)
    if aggregate.status in ("CANDIDATE", "VERIFIED"):
        valid = aggregate.question == review_question(pack)
        for member in pack.members:
            try:
                item = v.inspect_item(session, UUID(member["knowledge_id"]), actor)
            except v.KnowledgeConflict:
                valid = False
                continue
            valid = valid and item.status == "VERIFIED" and item.content_hash == member["content_hash"] and item.revision == member["revision"]
        if not valid:
            aggregate.status = "STALE"; aggregate.updated_at = datetime.now(timezone.utc)
            v.audit(session, aggregate, "KNOWLEDGE_STALE", reason="pack_binding_or_member_invalid")
            session.flush()
    return pack, aggregate


def decide(session, pack_id, payload, actor, operation):
    v.authorize(session, actor, review=True)
    pack, aggregate = inspect(session, pack_id, actor)
    v.decide(session, aggregate.id, payload, actor, operation)
    return pack, aggregate


def export(pack, aggregate):
    return {"pack_id": pack.id, "name": pack.name, "description": pack.description,
        "question": pack.question, "pack_version": aggregate.revision, "members": pack.members,
        "access_scope": aggregate.access_scope, "status": aggregate.status,
        "created_at": pack.created_at, "updated_at": aggregate.updated_at,
        "approved_at": aggregate.verified_at, "approved_by": aggregate.verified_by,
        "approval_revision_id": aggregate.approval_revision_id, "content_hash": aggregate.content_hash,
        "sources": aggregate.source_snapshot, "evidence": aggregate.evidence}


def lookup(session, request, actor):
    if actor is None or request.access_scope != "internal" or not v.eligible(request.query, ""):
        return None, "pack_ineligible"
    v.authorize(session, actor)
    ids = session.scalars(select(KnowledgePack.id).where(
        KnowledgePack.match_key == v.canonical_hash(v.normalized(request.query)))).all()
    valid = []
    for pack_id in ids:
        pack, aggregate = inspect(session, pack_id, actor)
        if aggregate.status == "VERIFIED" and v.eligible(request.query, aggregate.statement):
            valid.append((pack, aggregate))
    if len(valid) != 1:
        session.commit()
        return None, "pack_ambiguous" if len(valid) > 1 else "pack_missing_or_stale"
    pack, aggregate = valid[0]
    # Lock each governing revision through the final commit, including members.
    for member in pack.members:
        item = session.get(VerifiedKnowledge, UUID(member["knowledge_id"]))
        assert_still_approved_under_lock(session, item.approval_revision_id)
    assert_still_approved_under_lock(session, aggregate.approval_revision_id)
    state = v.state_for(aggregate); state["query"] = request.query
    v.audit(session, aggregate, "VERIFIED_KNOWLEDGE_SERVED", actor, reason="CAG_PATH")
    session.commit()
    return (state, {"pack_id": str(pack.id), "pack_version": aggregate.revision}), None
