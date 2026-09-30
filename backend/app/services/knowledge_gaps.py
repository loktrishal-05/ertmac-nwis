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


# Review lifecycle. Only authenticated human reviewers move a gap; no graph tool or model output can.
TRANSITIONS = {"assign": ("OPEN", "UNDER_REVIEW"), "resolve": ("OPEN", "UNDER_REVIEW"), "dismiss": ("OPEN", "UNDER_REVIEW")}


def run_gaps(session):
    """Gaps recorded by recent governed executions (the existing /knowledge-gaps source)."""
    from sqlalchemy import select
    from app.db.models.agent_run import AgentRun
    from app.db.models.agent_run_step import AgentRunStep
    rows = session.scalars(select(AgentRunStep).join(AgentRun).where(AgentRunStep.node_name == "execution_metadata")
        .order_by(AgentRun.created_at.desc(), AgentRunStep.id.desc()).limit(100)).all()
    unique = {}
    for row in rows:
        for gap in row.usage.get("execution", {}).get("knowledge_gaps", []):
            if len(unique) < 500:
                unique.setdefault(gap["gap_id"], {**gap, "run_id": str(row.run_id)})
    return unique


def export_gap(row):
    return {"gap_id": row.id, "subject": row.subject, "gap_type": row.gap_type, "required_evidence": row.required_evidence,
            "related_evidence": row.related_evidence, "origin": row.origin, "origin_reference": row.origin_reference,
            "access_scope": row.access_scope, "status": row.status, "created_by": row.created_by,
            "assigned_to": row.assigned_to, "resolved_by": row.resolved_by, "resolved_at": row.resolved_at,
            "resolution_knowledge_id": row.resolution_knowledge_id,
            "resolution_document_version_id": row.resolution_document_version_id,
            "resolution_note": row.resolution_note, "created_at": row.created_at, "updated_at": row.updated_at}


def listing(session, actor, status=None, limit=100, offset=0):
    from sqlalchemy import select
    from app.db.models import KnowledgeGap
    from app.services.verified_knowledge import authorize
    authorize(session, actor)
    stored = {row.id: row for row in session.scalars(select(KnowledgeGap).where(KnowledgeGap.access_scope == "internal")
                                                     .order_by(KnowledgeGap.updated_at.desc(), KnowledgeGap.id).limit(500))}
    detected = run_gaps(session)
    # Exact overlay prevents an old RESOLVED/DISMISSED row outside the recent sample being shown OPEN.
    if detected:
        stored.update({row.id: row for row in session.scalars(select(KnowledgeGap)
            .where(KnowledgeGap.id.in_(list(detected)), KnowledgeGap.access_scope == "internal"))})
    result = [{**gap, **(export_gap(stored[key]) if key in stored else {"status": "OPEN"})}
              for key, gap in detected.items()]
    seen = {g["gap_id"] for g in result}
    result += [export_gap(row) for key, row in stored.items() if key not in seen]
    result = sorted((g for g in result if status is None or g["status"] == status), key=lambda g: g["gap_id"])
    return result[offset:offset + limit]


def _audit(session, row, actor, role, previous, reason, knowledge=None):
    from app.services.audit import append_event
    # A resolution joins the linked knowledge's governed revision so it appears in that item's history.
    append_event(session, event_type="KNOWLEDGE_GAP_TRANSITION", actor_id=actor.id, actor_kind="user",
        action_revision_id=knowledge.approval_revision_id if knowledge else None,
        payload={"gap_id": row.id, "subject": row.subject, "gap_type": row.gap_type, "previous_status": previous,
                 "status": row.status, "actor_role": role, "reason": reason, "origin": row.origin,
                 "assigned_to": str(row.assigned_to) if row.assigned_to else None,
                 "resolution_knowledge_id": str(row.resolution_knowledge_id) if row.resolution_knowledge_id else None,
                 "resolution_document_version_id": str(row.resolution_document_version_id) if row.resolution_document_version_id else None})


def submit(session, payload, actor):
    from datetime import datetime, timezone
    from app.db.models import KnowledgeGap
    from app.services.verified_knowledge import KnowledgeConflict, authorize, check_origin
    role = authorize(session, actor)
    if payload.origin == "knowledge_gap":
        raise KnowledgeConflict("A gap cannot originate from another gap")
    check_origin(session, payload.origin, payload.origin_reference)
    key = canonical_hash({"subject": payload.subject, "gap_type": payload.gap_type})
    row = session.get(KnowledgeGap, key, with_for_update=True)
    if row is not None:
        return export_gap(row)  # Deduplicated by the same deterministic gap id; no second event.
    row = KnowledgeGap(id=key, subject=payload.subject, gap_type=payload.gap_type,
        required_evidence=payload.required_evidence, related_evidence=sorted(set(payload.related_evidence)),
        origin=payload.origin, origin_reference=payload.origin_reference, access_scope="internal",
        status="OPEN", created_by=actor.id, updated_at=datetime.now(timezone.utc))
    session.add(row)
    session.flush()
    _audit(session, row, actor, role, None, "submitted")
    session.flush()
    return export_gap(row)


def transition(session, gap_id, payload, actor, operation):
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.db.models import DocumentVersion, KnowledgeGap, User
    from app.services.approval import DecisionNotAllowed
    from app.services.verified_knowledge import KnowledgeConflict, authorize, inspect_item
    role = authorize(session, actor, review=True)
    if operation not in TRANSITIONS:
        raise KnowledgeConflict("Unknown gap operation")
    row = session.get(KnowledgeGap, gap_id, with_for_update=True, populate_existing=True)
    if row is None:
        # First review of a gap recorded by an execution: persist it from server-side run metadata only.
        found = run_gaps(session).get(gap_id)
        if found is None:
            raise KnowledgeConflict("Knowledge gap not found")
        row = KnowledgeGap(id=gap_id, subject=found["subject"][:200], gap_type=found["gap_type"][:80],
            required_evidence=found["required_evidence"], related_evidence=found.get("related_evidence", []),
            origin="query_execution", origin_reference=found.get("run_id"), access_scope="internal",
            status="OPEN", updated_at=datetime.now(timezone.utc))
        session.add(row)
        session.flush()
    if row.access_scope != "internal":
        raise KnowledgeConflict("Knowledge gap not found in authorized scope")
    if row.status not in TRANSITIONS[operation]:
        raise KnowledgeConflict(f"Gap cannot be {operation}d from {row.status}")
    previous, knowledge, now = row.status, None, datetime.now(timezone.utc)
    if operation == "assign":
        assignee = payload.assignee_id or actor.id
        if session.scalar(select(User.role).where(User.id == assignee)) not in ("reviewer", "admin"):
            raise DecisionNotAllowed("Gaps can only be assigned to a reviewer or admin")
        row.status, row.assigned_to = "UNDER_REVIEW", assignee
    else:
        if row.created_by == actor.id:
            raise DecisionNotAllowed("The submitter cannot close their own knowledge gap")
        if operation == "resolve":
            # Resolution needs human-verified knowledge or a current authoritative source, never an answer.
            if payload.knowledge_id:
                knowledge = inspect_item(session, payload.knowledge_id, actor)
                if knowledge.status != "VERIFIED":
                    raise KnowledgeConflict("Resolution requires currently verified knowledge")
            elif payload.document_version_id:
                version = session.get(DocumentVersion, payload.document_version_id)
                newer = version is not None and version.created_at is not None and session.scalar(
                    select(DocumentVersion.id).where(DocumentVersion.document_id == version.document_id,
                        DocumentVersion.id != version.id, DocumentVersion.created_at >= version.created_at).limit(1))
                if version is None or version.status != "indexed" or newer:
                    raise KnowledgeConflict("Resolution source is not a current indexed revision")
            else:
                raise KnowledgeConflict("Resolution requires verified knowledge or an authoritative source")
            row.resolution_knowledge_id, row.resolution_document_version_id = payload.knowledge_id, payload.document_version_id
        row.status = "RESOLVED" if operation == "resolve" else "DISMISSED"
        row.resolved_by, row.resolved_at = actor.id, now
        row.resolution_note = payload.comment
    row.updated_at = now
    _audit(session, row, actor, role, previous, payload.comment, knowledge)
    session.flush()
    return export_gap(row)
