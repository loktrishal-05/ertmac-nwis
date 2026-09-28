"""Enterprise knowledge: candidate origin/asset scope and persisted gap review state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016_enterprise_knowledge"
down_revision = "0015_durable_execution"
branch_labels = None
depends_on = None
OLD_EVENTS = ('GOVERNED_REVISION_CREATED', 'LOGIN_SUCCESS', 'LOGIN_FAILURE', 'APPROVAL_DECISION_APPROVE', 'APPROVAL_DECISION_REJECT', 'APPROVAL_DECISION_REVOKE', 'APPROVAL_AUTHORIZATION_DENIED', 'ADVISORY_RELEASE_SUCCESS', 'ADVISORY_RELEASE_DENIED', 'EVIDENCE_MANIFEST_CREATED', 'EVIDENCE_INTEGRITY_VERIFIED', 'EVIDENCE_INTEGRITY_FAILED', 'PREFLIGHT_OUT_OF_SCOPE_REFUSED', 'PREFLIGHT_INJECTION_REFUSED', 'PREFLIGHT_UNSAFE_ACTION_REFUSED', 'PREFLIGHT_SCOPE_DENIED', 'PREFLIGHT_CLARIFICATION_REQUIRED', 'KNOWLEDGE_CANDIDATE_CREATED', 'KNOWLEDGE_VERIFIED', 'KNOWLEDGE_STALE', 'KNOWLEDGE_REVOKED', 'VERIFIED_KNOWLEDGE_SERVED', 'OPERATOR_NOTE_CREATED', 'HANDOVER_GENERATED', 'COMPLIANCE_ASSESSMENT_GENERATED', 'KNOWLEDGE_GAPS_IDENTIFIED', 'VISUAL_INTERPRETATION_REQUESTED', 'PRODUCT_INTEGRATION_EVENT')


def upgrade():
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    # Extend the existing CHECK expression without importing mutable model code (0014 pattern).
    op.execute("""DO $$ DECLARE old_check text; BEGIN
      SELECT pg_get_constraintdef(oid) INTO old_check FROM pg_constraint
      WHERE conrelid = 'audit_events'::regclass AND conname = 'ck_audit_events_event_type';
      ALTER TABLE audit_events DROP CONSTRAINT ck_audit_events_event_type;
      EXECUTE 'ALTER TABLE audit_events ADD CONSTRAINT ck_audit_events_event_type CHECK ('
        || substring(old_check from 8 for length(old_check)-8)
        || ' OR event_type = ''KNOWLEDGE_GAP_TRANSITION'')';
    END $$""")
    op.add_column("verified_knowledge", sa.Column("origin", sa.String(40), nullable=False,
                                                  server_default="manual_submission"))
    op.add_column("verified_knowledge", sa.Column("origin_reference", sa.String(200)))
    op.add_column("verified_knowledge", sa.Column("asset_scope", json_type))
    op.create_table("knowledge_gaps",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("gap_type", sa.String(80), nullable=False),
        sa.Column("required_evidence", sa.Text(), nullable=False),
        sa.Column("related_evidence", json_type, nullable=False),
        sa.Column("origin", sa.String(40), nullable=False),
        sa.Column("origin_reference", sa.String(200)),
        sa.Column("access_scope", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("assigned_to", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("resolved_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_knowledge_id", sa.Uuid(), sa.ForeignKey("verified_knowledge.id")),
        sa.Column("resolution_document_version_id", sa.Uuid(), sa.ForeignKey("document_versions.id")),
        sa.Column("resolution_note", sa.Text()),
        sa.CheckConstraint("status IN ('OPEN','UNDER_REVIEW','RESOLVED','DISMISSED')", name="gap_status"))
    op.create_index("ix_knowledge_gaps_status", "knowledge_gaps", ["status"])


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM knowledge_gaps) OR EXISTS
        (SELECT 1 FROM audit_events WHERE event_type = 'KNOWLEDGE_GAP_TRANSITION') THEN
        RAISE EXCEPTION 'Knowledge gap history exists; refusing lossy downgrade';
      END IF;
    END $$""")
    op.drop_index("ix_knowledge_gaps_status", table_name="knowledge_gaps")
    op.drop_table("knowledge_gaps")
    op.drop_column("verified_knowledge", "asset_scope")
    op.drop_column("verified_knowledge", "origin_reference")
    op.drop_column("verified_knowledge", "origin")
    op.drop_constraint(op.f("ck_audit_events_event_type"), "audit_events", type_="check")
    op.create_check_constraint("event_type", "audit_events",
        "event_type IN (" + ",".join("'" + value + "'" for value in OLD_EVENTS) + ")")
