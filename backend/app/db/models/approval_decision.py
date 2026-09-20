"""Phase 5B immutable approval-decision ledger.

One row per decision EVENT (APPROVE, REJECT, or REVOKE) -- never a mutated
"status" column. This mirrors action_revision.py's append-only design and is
deliberate: "preserve decision history, never silently overwrite a prior
decision" (docs/phase5b.md) is exactly the shape a future Phase 5C audit
chain needs. A revision's current governance state is *computed* from this
ledger (see app.services.governance.get_governance_state), never stored.

At most one APPROVE-or-REJECT row and at most one REVOKE row may exist per
action_revision_id (the two partial unique indexes below); PostgreSQL
enforces this even under concurrent inserts. A REVOKE row's revoked_at/
revoked_by describe the revoke event itself (who revoked, when), and
revoked_decision_id names the APPROVE row it revokes -- not that this row was
revoked (a decision row is never mutated after insert).
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdentityMixin


class ApprovalDecision(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "approval_decisions"

    request_id: Mapped[UUID] = mapped_column(index=True)
    action_id: Mapped[UUID]
    # No inline ForeignKey here: the composite ForeignKeyConstraint below (on
    # action_revision_id + request_id together) is the real binding -- it
    # rejects "request A / approval B confusion" that a single-column FK
    # could not catch.
    action_revision_id: Mapped[UUID] = mapped_column(index=True)
    # Snapshot of the hashes verified at decision time -- provenance for a future
    # audit chain, not itself the authority (the service re-derives and compares
    # against a fresh reload of action_revisions before ever writing this row).
    canonical_request_hash: Mapped[str] = mapped_column(String(64))
    canonical_proposal_hash: Mapped[str] = mapped_column(String(64))
    approver_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    decision: Mapped[str] = mapped_column(String(20))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approval_purpose: Mapped[str] = mapped_column(String(100))
    policy_version: Mapped[str] = mapped_column(String(40))
    reviewer_comment: Mapped[str | None] = mapped_column(Text, default=None)
    # Only meaningful on an APPROVE row; release fails closed once passed.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Only ever set on a REVOKE row (see class docstring).
    revoked_decision_id: Mapped[UUID | None] = mapped_column(ForeignKey("approval_decisions.id"), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), default=None)

    __table_args__ = (
        ForeignKeyConstraint(["action_revision_id", "request_id"],
                            ["action_revisions.id", "action_revisions.request_id"],
                            name="fk_decision_exact_revision"),
        UniqueConstraint("id", "action_revision_id", name="uq_approval_decision_revision"),
        CheckConstraint("decision IN ('APPROVE', 'REJECT', 'REVOKE')", name="decision_kind"),
        CheckConstraint("length(canonical_request_hash) = 64 AND length(canonical_proposal_hash) = 64",
                        name="hash_lengths"),
        CheckConstraint(
            "(decision = 'REVOKE' AND revoked_decision_id IS NOT NULL AND revoked_at IS NOT NULL "
            "AND revoked_by IS NOT NULL) OR (decision != 'REVOKE' AND revoked_decision_id IS NULL "
            "AND revoked_at IS NULL AND revoked_by IS NULL)",
            name="revoke_fields_only_on_revoke",
        ),
        # At most one terminal review decision per revision, enforced even under
        # concurrent inserts -- the DB-level twin of Phase 5A's request-row lock.
        Index("uq_approval_decisions_terminal", "action_revision_id", unique=True,
              postgresql_where=text("decision IN ('APPROVE', 'REJECT')"),
              sqlite_where=text("decision IN ('APPROVE', 'REJECT')")),
        # At most one revoke per revision.
        Index("uq_approval_decisions_revoke", "action_revision_id", unique=True,
              postgresql_where=text("decision = 'REVOKE'"),
              sqlite_where=text("decision = 'REVOKE'")),
    )


def _immutable(mapper, connection, target):
    raise ValueError("Approval decisions are immutable; a revoke is a new decision row, never a mutation")


event.listen(ApprovalDecision, "before_update", _immutable)
event.listen(ApprovalDecision, "before_delete", _immutable)
