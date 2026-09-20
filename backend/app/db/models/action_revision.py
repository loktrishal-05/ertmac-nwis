"""Phase 5A immutable request binding and pending proposal revisions.

AgentAction remains the proposal identity. Legacy Approval is never authority.
PostgreSQL migration triggers also reject bulk/raw SQL updates and deletes.
"""
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdentityMixin


class GovernanceRequest(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "governance_requests"

    action_id: Mapped[UUID] = mapped_column(ForeignKey("agent_actions.id"), unique=True)
    initial_revision_id: Mapped[UUID]
    canonicalization_version: Mapped[str] = mapped_column(String(40))
    canonical_request: Mapped[str] = mapped_column(Text)
    canonical_request_hash: Mapped[str] = mapped_column(String(64))
    requester_context: Mapped[str] = mapped_column(Text)
    identity_status: Mapped[str] = mapped_column(String(20))
    # Phase 5B: the AUTHENTICATED session's user at request time, set once at
    # insert (never updated) when /query was called with a valid session
    # cookie; NULL for an unauthenticated /query call. This is the only
    # trustworthy requester identity self-approval checks may rely on --
    # requester_context above remains an unverified CLAIMED reference.
    requester_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    __table_args__ = (
        ForeignKeyConstraint(["initial_revision_id", "id"], ["action_revisions.id", "action_revisions.request_id"],
                             name="fk_governance_initial_revision", use_alter=True, deferrable=True, initially="DEFERRED"),
        UniqueConstraint("id", "action_id", "canonical_request_hash", name="uq_governance_request_action"),
        CheckConstraint("identity_status = 'UNVERIFIED'", name="unverified_identity"),
        CheckConstraint("canonicalization_version = 'workbench-json-v1'", name="canonical_version"),
        CheckConstraint("length(canonical_request_hash) = 64", name="request_hash_length"),
        CheckConstraint("canonical_request_hash = encode(sha256(convert_to(canonical_request, 'UTF8')), 'hex')",
                        name="request_hash_binding").ddl_if(dialect="postgresql"),
    )


class ActionRevision(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "action_revisions"

    request_id: Mapped[UUID] = mapped_column(index=True)
    action_id: Mapped[UUID]
    originating_run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    canonicalization_version: Mapped[str] = mapped_column(String(40))
    canonical_request_hash: Mapped[str] = mapped_column(String(64))
    canonical_proposal: Mapped[str] = mapped_column(Text)
    canonical_proposal_hash: Mapped[str] = mapped_column(String(64))
    evidence_binding_status: Mapped[str] = mapped_column(String(30))
    risk_category: Mapped[str] = mapped_column(String(40))
    policy_version: Mapped[str] = mapped_column(String(40))
    approval_purpose: Mapped[str] = mapped_column(String(100))
    governance_status: Mapped[str] = mapped_column(String(30))
    __table_args__ = (
        UniqueConstraint("id", "request_id", name="uq_action_revision_request"),
        ForeignKeyConstraint(["request_id", "action_id", "canonical_request_hash"],
                             ["governance_requests.id", "governance_requests.action_id", "governance_requests.canonical_request_hash"]),
        UniqueConstraint("request_id", "canonical_proposal_hash", "policy_version", name="uq_action_revision_content"),
        CheckConstraint("canonicalization_version = 'workbench-json-v1'", name="canonical_version"),
        CheckConstraint("governance_status = 'PENDING_REVIEW'", name="pending_only"),
        CheckConstraint("evidence_binding_status = 'PENDING_INTEGRITY'", name="unverified_evidence"),
        CheckConstraint("risk_category = 'HUMAN_REVIEW_REQUIRED'", name="risk_category"),
        CheckConstraint("approval_purpose = 'ADVISORY_DRAFT_REVIEW'", name="advisory_purpose"),
        CheckConstraint("length(policy_version) > 0", name="policy_version"),
        CheckConstraint("length(canonical_request_hash) = 64 AND length(canonical_proposal_hash) = 64", name="hash_lengths"),
        CheckConstraint("canonical_proposal_hash = encode(sha256(convert_to(canonical_proposal, 'UTF8')), 'hex')",
                        name="proposal_hash_binding").ddl_if(dialect="postgresql"),
    )


def _immutable(mapper, connection, target):
    raise ValueError("Governed bindings and revisions are immutable; create a new revision")


for _model in (GovernanceRequest, ActionRevision):
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)
