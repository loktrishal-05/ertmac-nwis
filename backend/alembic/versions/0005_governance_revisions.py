"""Phase 5A immutable governed revisions; legacy approvals are untouched."""
from alembic import op
import sqlalchemy as sa

revision = "0005_governance_revisions"
down_revision = "0004_agent_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "governance_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("initial_revision_id", sa.Uuid(), nullable=False),
        sa.Column("canonicalization_version", sa.String(40), nullable=False),
        sa.Column("canonical_request", sa.Text(), nullable=False),
        sa.Column("canonical_request_hash", sa.String(64), nullable=False),
        sa.Column("requester_context", sa.Text(), nullable=False),
        sa.Column("identity_status", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["action_id"], ["agent_actions.id"]),
        sa.UniqueConstraint("action_id"),
        sa.UniqueConstraint("id", "action_id", "canonical_request_hash", name="uq_governance_request_action"),
        sa.CheckConstraint("identity_status = 'UNVERIFIED'", name="unverified_identity"),
        sa.CheckConstraint("canonicalization_version = 'workbench-json-v1'", name="canonical_version"),
        sa.CheckConstraint("length(canonical_request_hash) = 64", name="request_hash_length"),
        sa.CheckConstraint("canonical_request_hash = encode(sha256(convert_to(canonical_request, 'UTF8')), 'hex')", name="request_hash_binding"),
    )
    op.create_table(
        "action_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("originating_run_id", sa.Uuid(), nullable=False),
        sa.Column("canonicalization_version", sa.String(40), nullable=False),
        sa.Column("canonical_request_hash", sa.String(64), nullable=False),
        sa.Column("canonical_proposal", sa.Text(), nullable=False),
        sa.Column("canonical_proposal_hash", sa.String(64), nullable=False),
        sa.Column("evidence_binding_status", sa.String(30), nullable=False),
        sa.Column("risk_category", sa.String(40), nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("approval_purpose", sa.String(100), nullable=False),
        sa.Column("governance_status", sa.String(30), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["originating_run_id"], ["agent_runs.id"]),
        sa.UniqueConstraint("id", "request_id", name="uq_action_revision_request"),
        sa.ForeignKeyConstraint(["request_id", "action_id", "canonical_request_hash"],
                                ["governance_requests.id", "governance_requests.action_id", "governance_requests.canonical_request_hash"]),
        sa.UniqueConstraint("request_id", "canonical_proposal_hash", "policy_version", name="uq_action_revision_content"),
        sa.CheckConstraint("canonicalization_version = 'workbench-json-v1'", name="canonical_version"),
        sa.CheckConstraint("governance_status = 'PENDING_REVIEW'", name="pending_only"),
        sa.CheckConstraint("evidence_binding_status = 'PENDING_INTEGRITY'", name="unverified_evidence"),
        sa.CheckConstraint("risk_category = 'HUMAN_REVIEW_REQUIRED'", name="risk_category"),
        sa.CheckConstraint("approval_purpose = 'ADVISORY_DRAFT_REVIEW'", name="advisory_purpose"),
        sa.CheckConstraint("length(policy_version) > 0", name="policy_version"),
        sa.CheckConstraint("length(canonical_request_hash) = 64 AND length(canonical_proposal_hash) = 64", name="hash_lengths"),
        sa.CheckConstraint("canonical_proposal_hash = encode(sha256(convert_to(canonical_proposal, 'UTF8')), 'hex')", name="proposal_hash_binding"),
    )
    op.create_index("ix_action_revisions_request_id", "action_revisions", ["request_id"])
    op.create_index("ix_action_revisions_originating_run_id", "action_revisions", ["originating_run_id"])
    op.create_foreign_key("fk_governance_initial_revision", "governance_requests", "action_revisions",
                          ["initial_revision_id", "id"], ["id", "request_id"], deferrable=True, initially="DEFERRED")
    op.execute("""
        CREATE FUNCTION reject_governed_revision_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'Governed bindings and revisions are immutable; create a new revision';
        END; $$
    """)
    for table in ("governance_requests", "action_revisions"):
        op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION reject_governed_revision_mutation()")


def downgrade():
    op.drop_constraint("fk_governance_initial_revision", "governance_requests", type_="foreignkey")
    for table in ("action_revisions", "governance_requests"):
        op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
    op.drop_table("action_revisions")
    op.drop_table("governance_requests")
    op.execute("DROP FUNCTION reject_governed_revision_mutation()")
