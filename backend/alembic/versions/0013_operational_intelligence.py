"""Operator reports and extended evidence/audit vocabulary; no plant authority."""
from alembic import op
import sqlalchemy as sa
revision = "0013_operational_intelligence"
down_revision = "0012_knowledge_packs"
branch_labels = None
depends_on = None
OLD_EVENTS = ('GOVERNED_REVISION_CREATED', 'LOGIN_SUCCESS', 'LOGIN_FAILURE', 'APPROVAL_DECISION_APPROVE', 'APPROVAL_DECISION_REJECT', 'APPROVAL_DECISION_REVOKE', 'APPROVAL_AUTHORIZATION_DENIED', 'ADVISORY_RELEASE_SUCCESS', 'ADVISORY_RELEASE_DENIED', 'EVIDENCE_MANIFEST_CREATED', 'EVIDENCE_INTEGRITY_VERIFIED', 'EVIDENCE_INTEGRITY_FAILED', 'PREFLIGHT_OUT_OF_SCOPE_REFUSED', 'PREFLIGHT_INJECTION_REFUSED', 'PREFLIGHT_UNSAFE_ACTION_REFUSED', 'PREFLIGHT_SCOPE_DENIED', 'PREFLIGHT_CLARIFICATION_REQUIRED', 'KNOWLEDGE_CANDIDATE_CREATED', 'KNOWLEDGE_VERIFIED', 'KNOWLEDGE_STALE', 'KNOWLEDGE_REVOKED', 'VERIFIED_KNOWLEDGE_SERVED')
NEW_EVENTS = OLD_EVENTS + ("OPERATOR_NOTE_CREATED", "HANDOVER_GENERATED", "COMPLIANCE_ASSESSMENT_GENERATED", "KNOWLEDGE_GAPS_IDENTIFIED", "VISUAL_INTERPRETATION_REQUESTED")
OLD_TYPES = ("document_chunk", "pid_region", "csv_row", "sensor_window")

def constraint(table, column, values):
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT ck_{table}_{column}")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_{column} CHECK ({column} IN (" + ",".join("'"+v+"'" for v in values) + "))")

def upgrade():
    constraint("audit_events", "event_type", NEW_EVENTS)
    constraint("evidence_manifest_items", "evidence_type", OLD_TYPES + ("operational_record",))
    op.create_table("operator_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("equipment_id", sa.Uuid(), sa.ForeignKey("equipment.id"), nullable=False),
        sa.Column("unit", sa.String(100)), sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("access_scope", sa.String(50), nullable=False),
        sa.Column("approval_revision_id", sa.Uuid(), sa.ForeignKey("action_revisions.id")))
    op.create_index("ix_operator_notes_equipment_id", "operator_notes", ["equipment_id"])

def downgrade():
    # Refuse destructive downgrade when immutable events/manifests still use these types.
    constraint("audit_events", "event_type", OLD_EVENTS)
    constraint("evidence_manifest_items", "evidence_type", OLD_TYPES)
    op.drop_table("operator_notes")
