"""Phase 5C tamper-evident audit chain: an append-only, hash-linked
audit_events ledger, a mutable audit_chain_heads lock/cursor table, and a
minimal audit_checkpoints snapshot table. No Phase 5A/5B table is touched."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_phase5c_audit_chain"
down_revision = "0006_phase5b_approvals"
branch_labels = None
depends_on = None

_EVENT_TYPES = (
    "GOVERNED_REVISION_CREATED", "LOGIN_SUCCESS", "LOGIN_FAILURE",
    "APPROVAL_DECISION_APPROVE", "APPROVAL_DECISION_REJECT", "APPROVAL_DECISION_REVOKE",
    "APPROVAL_AUTHORIZATION_DENIED", "ADVISORY_RELEASE_SUCCESS", "ADVISORY_RELEASE_DENIED",
)


def upgrade():
    op.create_table(
        "audit_chain_heads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chain_id", sa.String(100), nullable=False),
        sa.Column("next_sequence_number", sa.Integer(), nullable=False),
        sa.Column("head_hash", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chain_id"),
        sa.CheckConstraint("next_sequence_number >= 1", name="next_sequence_positive"),
        sa.CheckConstraint("length(head_hash) = 64", name="head_hash_length"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("chain_id", sa.String(100), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_kind", sa.String(20), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("action_revision_id", sa.Uuid(), nullable=True),
        sa.Column("decision_id", sa.Uuid(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("canonical_payload_hash", sa.String(64), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("canonical_event_json", sa.Text(), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["request_id"], ["governance_requests.id"]),
        sa.ForeignKeyConstraint(["action_revision_id"], ["action_revisions.id"]),
        sa.ForeignKeyConstraint(["decision_id"], ["approval_decisions.id"]),
        sa.UniqueConstraint("chain_id", "sequence_number", name="uq_audit_events_chain_sequence"),
        sa.UniqueConstraint("event_hash", name="uq_audit_events_hash"),
        sa.CheckConstraint("schema_version = 'phase5c-audit-v1'", name="schema_version"),
        sa.CheckConstraint("actor_kind IN ('user', 'system', 'anonymous')", name="actor_kind"),
        sa.CheckConstraint(
            "event_type IN (" + ", ".join(f"'{value}'" for value in _EVENT_TYPES) + ")", name="event_type",
        ),
        sa.CheckConstraint("sequence_number >= 1", name="sequence_positive"),
        sa.CheckConstraint(
            "length(canonical_payload_hash) = 64 AND length(previous_hash) = 64 AND length(event_hash) = 64",
            name="hash_lengths",
        ),
        sa.CheckConstraint("event_hash = encode(sha256(convert_to(canonical_event_json, 'UTF8')), 'hex')",
                          name="event_hash_binding"),
    )
    op.create_index("ix_audit_events_chain_id", "audit_events", ["chain_id"])
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])
    op.create_index("ix_audit_events_action_revision_id", "audit_events", ["action_revision_id"])
    op.create_index("ix_audit_events_decision_id", "audit_events", ["decision_id"])

    op.create_table(
        "audit_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("chain_id", sa.String(100), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("head_hash", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("sequence_number >= 1", name="sequence_positive"),
        sa.CheckConstraint("length(head_hash) = 64", name="head_hash_length"),
    )
    op.create_index("ix_audit_checkpoints_chain_id", "audit_checkpoints", ["chain_id"])

    op.execute("""
        CREATE FUNCTION reject_audit_event_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'Audit events are append-only and immutable; they can never be updated or deleted';
        END; $$
    """)
    for table in ("audit_events", "audit_checkpoints"):
        op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation()")


def downgrade():
    for table in ("audit_checkpoints", "audit_events"):
        op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
    op.execute("DROP FUNCTION reject_audit_event_mutation()")
    op.drop_table("audit_checkpoints")
    op.drop_table("audit_events")
    op.drop_table("audit_chain_heads")
