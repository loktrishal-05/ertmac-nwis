"""Bounded operational projections. Raw checkpoints, prompts and tool results never leave here."""
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import HTTPException, Query
from sqlalchemy import case, exists, select, func
from app.core.config import settings
from app.db.models import ActionRevision, ApprovalDecision, AgentRun, AgentRunStep, GovernanceRequest
from app.db.models.durable_execution import DurableExecution, ExecutionOperation
from app.services import durable_execution

def now():
    return datetime.now(timezone.utc)

def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def validate_range(start, end):
    start, end = utc(start) if start else None, utc(end) if end else None
    if start and end and (end <= start or end - start > timedelta(days=366)):
        raise HTTPException(422, "Time range must be positive and at most 366 days.")
    return start, end

def window(range: Literal["24h", "7d", "30d", "custom"] = "7d",
           start: datetime | None = None, end: datetime | None = None):
    if range == "custom":
        if start is None or end is None:
            raise HTTPException(422, "Custom range requires start and end.")
    else:
        if start is not None or end is not None:
            raise HTTPException(422, "Use custom range with explicit start and end.")
        end = now()
        start = end - {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}[range]
    return validate_range(start, end)

def page(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=10000)):
    return limit, offset

def envelope(items, limit, offset, as_of=None):
    return {"items": items[:limit], "sample_size": min(len(items), limit), "as_of": as_of or now(),
            "limit": limit, "offset": offset, "has_more": len(items) > limit,
            "next_offset": offset + limit if len(items) > limit else None}

def approval_state(at):
    # Same precedence as governance._ledger_state; this projection grants no authority.
    rev = ActionRevision.id
    def has(*conditions):
        return exists(select(ApprovalDecision.id).where(ApprovalDecision.action_revision_id == rev, *conditions))
    return case(
        (has(ApprovalDecision.decision == "REJECT"), "REJECTED"),
        (has(ApprovalDecision.decision == "APPROVE") & has(ApprovalDecision.decision == "REVOKE"), "REVOKED"),
        (has(ApprovalDecision.decision == "APPROVE", ApprovalDecision.expires_at <= at), "EXPIRED"),
        (has(ApprovalDecision.decision == "APPROVE"), "APPROVED"), else_="PENDING_REVIEW")

def approvals(session, actor, view, status, limit, offset, start=None, end=None):
    at = now()
    state = approval_state(at)
    query = (select(ActionRevision, GovernanceRequest.requester_user_id, AgentRun.route, AgentRun.model,
                    DurableExecution.id, state.label("state"))
             .join(GovernanceRequest, GovernanceRequest.id == ActionRevision.request_id)
             .join(AgentRun, AgentRun.id == ActionRevision.originating_run_id)
             .outerjoin(DurableExecution, DurableExecution.id == ActionRevision.request_id))
    if view == "pending":
        query = query.where(state == "PENDING_REVIEW",
            (GovernanceRequest.requester_user_id.is_(None)) | (GovernanceRequest.requester_user_id != actor.id))
    elif view == "history":
        query = query.where(state != "PENDING_REVIEW")
    if status:
        query = query.where(state == status)
    start, end = validate_range(start, end)
    if start:
        query = query.where(ActionRevision.created_at >= start)
    if end:
        query = query.where(ActionRevision.created_at < end)
    rows = session.execute(query.order_by(ActionRevision.created_at.desc(), ActionRevision.id.desc())
                           .offset(offset).limit(limit)).all()
    ids = [r[0].id for r in rows]
    selected_models = {}
    run_ids = [r[0].originating_run_id for r in rows]
    if run_ids:
        for ident, usage in session.execute(select(AgentRunStep.run_id, AgentRunStep.usage)
                .where(AgentRunStep.run_id.in_(run_ids), AgentRunStep.node_name == "execution_metadata")
                .order_by(AgentRunStep.run_id, AgentRunStep.step_index.desc(), AgentRunStep.id.desc())
                .limit(limit * 2)):
            execution = (usage or {}).get("execution", {})
            selected_models.setdefault(ident, execution.get("model_selected") or execution.get("selected_model"))
    decisions = {}
    if ids:
        for d in session.scalars(select(ApprovalDecision).where(ApprovalDecision.action_revision_id.in_(ids))
                                 .order_by(ApprovalDecision.decided_at, ApprovalDecision.id)):
            decisions.setdefault(d.action_revision_id, []).append(d)
    # Evidence summaries use the existing immutable manifest, never the raw proposal.
    from app.db.models import EvidenceManifest, EvidenceManifestItem
    evidence = dict(session.execute(select(EvidenceManifest.action_revision_id, func.count(EvidenceManifestItem.id))
        .outerjoin(EvidenceManifestItem, EvidenceManifestItem.manifest_id == EvidenceManifest.id)
        .where(EvidenceManifest.action_revision_id.in_(ids))
        .group_by(EvidenceManifest.action_revision_id)).all()) if ids else {}
    return [{"action_revision_id": r.id, "request_id": r.request_id, "requester_user_id": owner,
             "route": route, "selected_model": selected_models.get(r.originating_run_id),
             "configured_model": model, "execution_id": execution,
             "created_at": r.created_at, "governance_status": current,
             "action_class": r.approval_purpose, "governance_reason": r.risk_category,
             "evidence_count": evidence.get(r.id), "policy_version": r.policy_version,
             "decided_at": decisions[r.id][-1].decided_at if r.id in decisions else None,
             "reviewer_id": decisions[r.id][-1].approver_id if r.id in decisions else None,
             "decisions": [{"decision_id": d.id, "decision": d.decision, "decided_at": d.decided_at,
                            "reviewer_id": d.approver_id, "expires_at": d.expires_at}
                           for d in decisions.get(r.id, [])]} for r, owner, route, model, execution, current in rows]

def execution_summaries(session, rows):
    ids = [r.id for r in rows]
    counts = {}
    if ids:
        for ident, status, count in session.execute(select(ExecutionOperation.execution_id, ExecutionOperation.status,
                func.count()).where(ExecutionOperation.execution_id.in_(ids))
                .group_by(ExecutionOperation.execution_id, ExecutionOperation.status)):
            counts.setdefault(ident, {})[status] = count
    bindings = session.execute(select(GovernanceRequest.id, ActionRevision.id, approval_state(now()))
        .join(ActionRevision, ActionRevision.id == GovernanceRequest.initial_revision_id)
        .where(GovernanceRequest.id.in_(ids))).all() if ids else []
    states = {request_id: state for request_id, _, state in bindings}
    revisions = {request_id: revision_id for request_id, revision_id, _ in bindings}
    routes = dict(session.execute(select(AgentRun.id, AgentRun.route).where(AgentRun.id.in_(ids))).all()) if ids else {}
    items = []
    for r in rows:
        state = states.get(r.id)
        can_resume = (r.status in ("PENDING", "INTERRUPTED", "FAILED", "WAITING_APPROVAL")
            and r.retry_class not in ("FAIL_CLOSED", "NON_RETRYABLE_VALIDATION")
            and r.revision == 1 and r.selected_model == settings.primary_model
            and (r.status != "WAITING_APPROVAL" or state in ("APPROVED", "REJECTED", "REVOKED", "EXPIRED")))
        items.append({**{k: getattr(r, k) for k in ("status", "current_node", "retry_class", "resume_count",
            "retry_count", "checkpoint_version", "selected_model", "execution_path", "created_at", "updated_at", "revision")},
            "execution_id": r.id, "user_id": r.user_id, "governance_status": state,
            "action_revision_id": revisions.get(r.id), "route": routes.get(r.id),
            "waiting_approval": r.status == "WAITING_APPROVAL", "resume_available": can_resume,
            "resume_requires_server_recheck": True, "receipt_status_counts": counts.get(r.id, {})})
    return items

def execution_list(session, actor, limit, offset, status=None, start=None, end=None):
    query = select(DurableExecution)
    if actor.role != "admin":
        query = query.where(DurableExecution.user_id == actor.id)
    if status:
        query = query.where(DurableExecution.status == status)
    start, end = validate_range(start, end)
    if start:
        query = query.where(DurableExecution.created_at >= start)
    if end:
        query = query.where(DurableExecution.created_at < end)
    rows = session.scalars(query.order_by(DurableExecution.created_at.desc(), DurableExecution.id.desc())
                           .offset(offset).limit(limit + 1)).all()
    return envelope(execution_summaries(session, rows), limit, offset)

def execution_detail(session, ident, actor, limit, offset):
    row = durable_execution.authorize(session, ident, actor)
    # Retain existing abandoned-worker reconciliation, but never return stored response/checkpoint bodies.
    if row.status == "RUNNING":
        durable_execution.status(session, ident, actor)
        session.refresh(row)
    item = execution_summaries(session, [row])[0]
    ops = session.scalars(select(ExecutionOperation).where(ExecutionOperation.execution_id == ident)
        .order_by(ExecutionOperation.started_at, ExecutionOperation.key).offset(offset).limit(limit + 1)).all()
    timeline = []
    for op in ops:
        parts = op.key.split(":")
        kind = parts[0] if parts[0] in ("node", "tool") else "operation"
        timeline.append({"kind": kind, "node": parts[1] if kind in ("node", "tool") and len(parts) > 1 else None,
            "tool": parts[3] if kind == "tool" and len(parts) > 3 else None, "status": op.status,
            "retry_class": op.retry_class, "attempts": op.attempts,
            "started_at": op.started_at, "finished_at": op.finished_at})
    item.update(as_of=now(), timeline=envelope(timeline, limit, offset),
                timeline_semantics="Latest persisted receipt per operation; attempts are counts, not an event history.")
    return item
