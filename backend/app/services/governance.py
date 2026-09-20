"""The common post-validation governance boundary. No approval or release in 5A.

Raw graph outputs are advisory computation, never a release credential.
This service owns persistence and derives response metadata from stored rows.
"""
import json
import re
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.agents.enforcement import operational_action_text
from app.agents.tracing import record_run
from app.core.config import settings
from app.db.models import ActionRevision, Agent, AgentAction, AgentRun, GovernanceRequest
from app.schemas.query import QueryRequest, QueryResponse
from app.services.canonicalization import CANONICALIZATION_VERSION, canonical_hash, canonical_json

POLICY_VERSION = "governance-5a-v1"
_NAMESPACE = UUID("8a73e583-c8cd-4d66-94ed-f55636683466")
_AGENT_ID = uuid5(_NAMESPACE, "governance-owner")
_AUTHORITY_FIELDS = frozenset({
    "approved", "approval_status", "approval_required", "human_approval_required", "authorized",
    "authorization", "action_class", "safe_to_proceed", "permission_granted", "operator_approved",
    "governance_status", "action_revision_id", "human_review_required", "verified_principal",
})
_CHANGE = re.compile(r"\b(?:increase|decrease|adjust|set|change|reduce|raise|lower|disable|enable|execute)\b", re.I)


class GovernanceConflict(ValueError):
    """An idempotency key was reused for a different request/context."""


class ReleaseNotAllowed(PermissionError):
    """No authenticated approval authority or release workflow exists in 5A."""


def _requirements(value) -> bool:
    if isinstance(value, dict):
        # Advisory metadata can only increase caution; it never grants authority.
        return (value.get("human_approval_required") is True or value.get("approval_required") is True
                or value.get("action_class") in {"inspection", "process_change", "isolation", "shutdown"}
                or any(_requirements(item) for item in value.values()))
    return isinstance(value, list) and any(_requirements(item) for item in value)


def _without_authority(value):
    if isinstance(value, dict):
        return {key: _without_authority(item) for key, item in value.items() if key not in _AUTHORITY_FIELDS}
    if isinstance(value, list):
        return [_without_authority(item) for item in value]
    return value


def evaluate_governance(request: QueryRequest, state: dict) -> str:
    """Only known informational shapes qualify; any requirement wins.

    All assessment/recommendation schemas and unknown outputs require review,
    regardless of routing/model labels. Phrase scans can increase caution only.
    """
    result = state.get("agent_result") or {}
    if _requirements(state):
        return "PENDING_REVIEW"
    if result.get("schema") not in {"S1", "S3", "S5"}:
        return "PENDING_REVIEW"
    if result.get("schema") == "S5":
        return "INFORMATIONAL"  # validated deterministic refusals offer no action
    text = canonical_json({"query": request.query, "output": _without_authority(result)})
    if operational_action_text(text) or _CHANGE.search(text):
        return "PENDING_REVIEW"
    return "INFORMATIONAL"


def _request_payload(request):
    return {"query": request.query, "access_scope": request.access_scope,
            "requester": {"claimed_reference": request.requester_reference, "identity_status": "UNVERIFIED"}}


def _proposal_payload(state):
    # Timings/run IDs are provenance, not proposal content. Evidence is a snapshot,
    # not a claim of verified source integrity (Phase 5D).
    return {"route": state.get("route"), "agent_result": state.get("agent_result"),
            "evidence": [ref.model_dump(mode="json") if hasattr(ref, "model_dump") else ref
                         for ref in state.get("evidence", [])], "warnings": state.get("warnings", [])}


def _insert_once(session, model, values):
    dialect = session.get_bind().dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise ValueError("Unsupported governance database")
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    session.execute(insert(model).values(**values).on_conflict_do_nothing())


def _check_request(binding, request):
    if binding.canonical_request_hash != canonical_hash(_request_payload(request)):
        raise GovernanceConflict("request_id is already bound to different request content or claimed context")


def _first_revision(session, request_id):
    binding = session.get(GovernanceRequest, request_id)
    return session.get(ActionRevision, binding.initial_revision_id)


def get_governance_state(session, revision_id: UUID) -> str:
    # Load a fresh stored row; caller-supplied objects/legacy approvals are not authority.
    row = session.execute(select(ActionRevision.governance_status).where(ActionRevision.id == revision_id)).scalar_one_or_none()
    if row != "PENDING_REVIEW":
        raise ReleaseNotAllowed("No recognized governed revision")
    return row


def assert_release_allowed(session, revision_id: UUID) -> None:
    get_governance_state(session, revision_id)
    raise ReleaseNotAllowed("PENDING_REVIEW cannot be released: authenticated human approval is not implemented")


def create_revision(session, request: QueryRequest, state: dict, *, replay: bool = False) -> ActionRevision:
    """Atomically persist a governed draft; never accept a caller's status/policy/hash.

    A request-row lock serializes revisions for one request in PostgreSQL.
    Explicit service edits use replay=False; /query retries use replay=True.
    Caller owns commit/rollback, so provenance and the revision commit together.
    """
    request_id = request.request_id or uuid4()
    payload = _request_payload(request)
    request_hash = canonical_hash(payload)
    proposal = _proposal_payload(state)
    proposal_hash = canonical_hash(proposal)
    revision_id = uuid5(request_id, CANONICALIZATION_VERSION + ":" + POLICY_VERSION + ":" + proposal_hash)
    existing = session.get(GovernanceRequest, request_id)
    if existing:
        _check_request(existing, request)
    if evaluate_governance(request, state) != "PENDING_REVIEW" and existing is None:
        raise ValueError("Informational output does not create an actionable approval")

    action_id = uuid5(_NAMESPACE, str(request_id))
    _insert_once(session, Agent, {"id": _AGENT_ID, "name": "Governance proposal owner", "agent_type": "governance",
                                 "status": "implemented"})
    _insert_once(session, AgentAction, {"id": action_id, "agent_id": _AGENT_ID,
                                      "action_type": "advisory_proposal", "status": "pending_review"})
    _insert_once(session, GovernanceRequest, {
        "id": request_id, "action_id": action_id, "initial_revision_id": revision_id,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "canonical_request": canonical_json(payload), "canonical_request_hash": request_hash,
        "requester_context": canonical_json(payload["requester"]), "identity_status": "UNVERIFIED",
    })
    binding = session.scalars(select(GovernanceRequest).where(GovernanceRequest.id == request_id).with_for_update()).one()
    _check_request(binding, request)
    previous = _first_revision(session, request_id)
    if replay and previous is not None:
        return previous

    previous = session.get(ActionRevision, revision_id)
    if previous is not None:
        return previous
    run_id = UUID(state["run_id"])
    if session.get(AgentRun, run_id) is None:
        record_run(session, state, status="ok", model=settings.model_name, runtime=settings.model_runtime,
                   required=True, commit=False)
    _insert_once(session, ActionRevision, {
        "id": revision_id, "request_id": request_id, "action_id": action_id, "originating_run_id": run_id,
        "canonicalization_version": CANONICALIZATION_VERSION, "canonical_request_hash": request_hash,
        "canonical_proposal": canonical_json(proposal), "canonical_proposal_hash": proposal_hash,
        "evidence_binding_status": "PENDING_INTEGRITY", "risk_category": "HUMAN_REVIEW_REQUIRED",
        "policy_version": POLICY_VERSION, "approval_purpose": "ADVISORY_DRAFT_REVIEW", "governance_status": "PENDING_REVIEW",
    })
    return session.get(ActionRevision, revision_id)


def _draft_response(revision) -> QueryResponse:
    proposal = json.loads(revision.canonical_proposal)["payload"]
    return QueryResponse(
        request_id=revision.request_id, run_id=str(revision.originating_run_id), route=proposal["route"],
        route_confidence=None, route_reasoning=None, agent_result=_without_authority(proposal["agent_result"]),
        evidence=proposal["evidence"], warnings=proposal["warnings"], human_approval_required=True,
        action_class=None, timings={}, governance_status=revision.governance_status,
        action_revision_id=revision.id, human_review_required=True, presentation="DRAFT",
        canonicalization_version=revision.canonicalization_version,
        canonical_request_hash=revision.canonical_request_hash, canonical_proposal_hash=revision.canonical_proposal_hash,
        evidence_binding_status=revision.evidence_binding_status, policy_version=revision.policy_version,
    )


def replay_request(session, request: QueryRequest) -> QueryResponse | None:
    if request.request_id is None:
        return None
    binding = session.get(GovernanceRequest, request.request_id)
    if binding is None:
        return None
    _check_request(binding, request)
    revision = _first_revision(session, binding.id)
    if revision is None:
        raise GovernanceConflict("Request has no committed revision")
    return _draft_response(revision)


def govern_response(session, request: QueryRequest, state: dict) -> QueryResponse:
    """Only public response assembler; commit before returning a pending draft."""
    replayed = replay_request(session, request)
    if replayed is not None:
        return replayed
    if evaluate_governance(request, state) == "PENDING_REVIEW":
        try:
            revision = create_revision(session, request, state, replay=True)
            response = _draft_response(revision)
            session.commit()
            return response
        except Exception:
            session.rollback()
            raise
    record_run(session, state, status="error" if state.get("errors") else "ok",
               model=settings.model_name, runtime=settings.model_runtime,
               error="; ".join(state.get("errors", [])) or None)
    return QueryResponse(
        request_id=request.request_id or uuid4(), run_id=state["run_id"], route=state.get("route"),
        route_confidence=state.get("route_confidence"), route_reasoning=state.get("route_reasoning"),
        agent_result=_without_authority(state.get("agent_result")), evidence=state.get("evidence", []),
        warnings=state.get("warnings", []), human_approval_required=False, action_class=None,
        timings={"started_at": state.get("started_at"), "finished_at": state.get("finished_at"),
                 "steps": [{"node_name": step.get("node_name"), "duration_ms": step.get("duration_ms")}
                           for step in state.get("step_records", [])]},
        governance_status="INFORMATIONAL", human_review_required=False, presentation="INFORMATIONAL",
    )
