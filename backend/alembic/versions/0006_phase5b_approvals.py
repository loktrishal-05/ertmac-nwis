"""Phase 5B authenticated human approval workflow: users gain a password
hash, server-issued sessions, an immutable approval-decision ledger, and a
requester_user_id column on governance_requests."""
from alembic import op
import sqlalchemy as sa

revision = "0006_phase5b_approvals"
down_revision = "0005_governance_revisions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.alter_column("users", "role", server_default="requester")

    op.add_column("governance_requests", sa.Column("requester_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_governance_requests_requester_user_id", "governance_requests", "users",
                          ["requester_user_id"], ["id"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("action_revision_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_request_hash", sa.String(64), nullable=False),
        sa.Column("canonical_proposal_hash", sa.String(64), nullable=False),
        sa.Column("approver_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approval_purpose", sa.String(100), nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("reviewer_comment", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_decision_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["action_revision_id", "request_id"],
                                ["action_revisions.id", "action_revisions.request_id"],
                                name="fk_decision_exact_revision"),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["revoked_decision_id"], ["approval_decisions.id"]),
        sa.UniqueConstraint("id", "action_revision_id", name="uq_approval_decision_revision"),
        sa.CheckConstraint("decision IN ('APPROVE', 'REJECT', 'REVOKE')", name="decision_kind"),
        sa.CheckConstraint("length(canonical_request_hash) = 64 AND length(canonical_proposal_hash) = 64",
                          name="hash_lengths"),
        sa.CheckConstraint(
            "(decision = 'REVOKE' AND revoked_decision_id IS NOT NULL AND revoked_at IS NOT NULL "
            "AND revoked_by IS NOT NULL) OR (decision != 'REVOKE' AND revoked_decision_id IS NULL "
            "AND revoked_at IS NULL AND revoked_by IS NULL)",
            name="revoke_fields_only_on_revoke",
        ),
    )
    op.create_index("ix_approval_decisions_request_id", "approval_decisions", ["request_id"])
    op.create_index("ix_approval_decisions_action_revision_id", "approval_decisions", ["action_revision_id"])
    op.create_index("ix_approval_decisions_approver_id", "approval_decisions", ["approver_id"])
    op.create_index("uq_approval_decisions_terminal", "approval_decisions", ["action_revision_id"], unique=True,
                    postgresql_where=sa.text("decision IN ('APPROVE', 'REJECT')"))
    op.create_index("uq_approval_decisions_revoke", "approval_decisions", ["action_revision_id"], unique=True,
                    postgresql_where=sa.text("decision = 'REVOKE'"))

    op.execute("CREATE TRIGGER immutable_approval_decisions BEFORE UPDATE OR DELETE ON approval_decisions "
               "FOR EACH ROW EXECUTE FUNCTION reject_governed_revision_mutation()")


def downgrade():
    op.execute("DROP TRIGGER immutable_approval_decisions ON approval_decisions")
    op.drop_table("approval_decisions")
    op.drop_table("auth_sessions")
    op.drop_constraint("fk_governance_requests_requester_user_id", "governance_requests", type_="foreignkey")
    op.drop_column("governance_requests", "requester_user_id")
    op.alter_column("users", "role", server_default="viewer")
    op.drop_column("users", "password_hash")
