"""Phase 5D cryptographic evidence integrity: immutable evidence_manifests /
evidence_manifest_items tables binding a governed ActionRevision to its exact
evidence snapshot, plus widening audit_events.event_type to admit the three
new Phase 5D event types. No Phase 5A/5B/5C table structure is otherwise
touched."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_phase5d_evidence_integrity"
down_revision = "0007_phase5c_audit_chain"
branch_labels = None
depends_on = None

_OLD_EVENT_TYPES = (
    "GOVERNED_REVISION_CREATED", "LOGIN_SUCCESS", "LOGIN_FAILURE",
    "APPROVAL_DECISION_APPROVE", "APPROVAL_DECISION_REJECT", "APPROVAL_DECISION_REVOKE",
    "APPROVAL_AUTHORIZATION_DENIED", "ADVISORY_RELEASE_SUCCESS", "ADVISORY_RELEASE_DENIED",
)
_NEW_EVENT_TYPES = _OLD_EVENT_TYPES + (
    "EVIDENCE_MANIFEST_CREATED", "EVIDENCE_INTEGRITY_VERIFIED", "EVIDENCE_INTEGRITY_FAILED",
)
_EVIDENCE_TYPES = ("document_chunk", "pid_region", "csv_row", "sensor_window")


def upgrade():
    op.create_table(
        "evidence_manifests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("action_revision_id", sa.Uuid(), nullable=False),
        sa.Column("manifest_version", sa.String(40), nullable=False),
        sa.Column("canonical_manifest", sa.Text(), nullable=False),
        sa.Column("canonical_manifest_hash", sa.String(64), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("integrity_status", sa.String(30), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["action_revision_id"], ["action_revisions.id"]),
        sa.CheckConstraint("manifest_version = 'phase5d-evidence-v1'", name="manifest_version"),
        sa.CheckConstraint("integrity_status = 'PENDING_INTEGRITY'", name="frozen_pending_integrity"),
        sa.CheckConstraint("item_count >= 0", name="item_count_non_negative"),
        sa.CheckConstraint("length(canonical_manifest_hash) = 64", name="manifest_hash_length"),
        sa.CheckConstraint("canonical_manifest_hash = encode(sha256(convert_to(canonical_manifest, 'UTF8')), 'hex')",
                          name="manifest_hash_binding"),
    )
    op.create_index("ix_evidence_manifests_action_revision_id", "evidence_manifests", ["action_revision_id"],
                    unique=True)

    op.create_table(
        "evidence_manifest_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("manifest_id", sa.Uuid(), nullable=False),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("evidence_type", sa.String(30), nullable=False),
        sa.Column("evidence_id", sa.String(80), nullable=False),
        sa.Column("source_identifier", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column("canonical_item_hash", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["manifest_id"], ["evidence_manifests.id"]),
        sa.UniqueConstraint("manifest_id", "item_index", name="uq_evidence_item_manifest_index"),
        sa.CheckConstraint(
            "evidence_type IN (" + ", ".join(f"'{value}'" for value in _EVIDENCE_TYPES) + ")", name="evidence_type",
        ),
        sa.CheckConstraint(
            "length(source_hash) = 64 AND length(content_hash) = 64 AND length(canonical_item_hash) = 64",
            name="hash_lengths",
        ),
    )
    op.create_index("ix_evidence_manifest_items_manifest_id", "evidence_manifest_items", ["manifest_id"])

    op.execute("""
        CREATE FUNCTION reject_evidence_manifest_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'Evidence manifests are immutable once frozen; create a new governed revision';
        END; $$
    """)
    for table in ("evidence_manifests", "evidence_manifest_items"):
        op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION reject_evidence_manifest_mutation()")

    op.execute("ALTER TABLE audit_events DROP CONSTRAINT ck_audit_events_event_type")
    op.execute(
        "ALTER TABLE audit_events ADD CONSTRAINT ck_audit_events_event_type CHECK (event_type IN ("
        + ", ".join(f"'{value}'" for value in _NEW_EVENT_TYPES) + "))"
    )


def downgrade():
    op.execute("ALTER TABLE audit_events DROP CONSTRAINT ck_audit_events_event_type")
    op.execute(
        "ALTER TABLE audit_events ADD CONSTRAINT ck_audit_events_event_type CHECK (event_type IN ("
        + ", ".join(f"'{value}'" for value in _OLD_EVENT_TYPES) + "))"
    )
    for table in ("evidence_manifest_items", "evidence_manifests"):
        op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
    op.execute("DROP FUNCTION reject_evidence_manifest_mutation()")
    op.drop_table("evidence_manifest_items")
    op.drop_table("evidence_manifests")
