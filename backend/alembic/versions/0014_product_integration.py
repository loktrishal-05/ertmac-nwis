"""Scoped integration audit and durable webhook replay prevention."""
from alembic import op
import sqlalchemy as sa

revision = "0014_product_integration"
down_revision = "0013_operational_intelligence"
branch_labels = None
depends_on = None
OLD_EVENTS = ('GOVERNED_REVISION_CREATED', 'LOGIN_SUCCESS', 'LOGIN_FAILURE', 'APPROVAL_DECISION_APPROVE', 'APPROVAL_DECISION_REJECT', 'APPROVAL_DECISION_REVOKE', 'APPROVAL_AUTHORIZATION_DENIED', 'ADVISORY_RELEASE_SUCCESS', 'ADVISORY_RELEASE_DENIED', 'EVIDENCE_MANIFEST_CREATED', 'EVIDENCE_INTEGRITY_VERIFIED', 'EVIDENCE_INTEGRITY_FAILED', 'PREFLIGHT_OUT_OF_SCOPE_REFUSED', 'PREFLIGHT_INJECTION_REFUSED', 'PREFLIGHT_UNSAFE_ACTION_REFUSED', 'PREFLIGHT_SCOPE_DENIED', 'PREFLIGHT_CLARIFICATION_REQUIRED', 'KNOWLEDGE_CANDIDATE_CREATED', 'KNOWLEDGE_VERIFIED', 'KNOWLEDGE_STALE', 'KNOWLEDGE_REVOKED', 'VERIFIED_KNOWLEDGE_SERVED', 'OPERATOR_NOTE_CREATED', 'HANDOVER_GENERATED', 'COMPLIANCE_ASSESSMENT_GENERATED', 'KNOWLEDGE_GAPS_IDENTIFIED', 'VISUAL_INTERPRETATION_REQUESTED')


def upgrade():
    # Extend the existing CHECK expression without importing mutable model code.
    op.execute("""DO $$ DECLARE old_check text; BEGIN
      SELECT pg_get_constraintdef(oid) INTO old_check FROM pg_constraint
      WHERE conrelid = 'audit_events'::regclass AND conname = 'ck_audit_events_event_type';
      ALTER TABLE audit_events DROP CONSTRAINT ck_audit_events_event_type;
      EXECUTE 'ALTER TABLE audit_events ADD CONSTRAINT ck_audit_events_event_type CHECK ('
        || substring(old_check from 8 for length(old_check)-8)
        || ' OR event_type = ''PRODUCT_INTEGRATION_EVENT'')';
    END $$""")
    op.create_table("automation_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("kind", sa.String(60), nullable=False))


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM automation_receipts) OR EXISTS
        (SELECT 1 FROM audit_events WHERE event_type = 'PRODUCT_INTEGRATION_EVENT') THEN
        RAISE EXCEPTION 'Integration history exists; refusing lossy downgrade';
      END IF;
    END $$""")
    op.drop_table("automation_receipts")
    op.drop_constraint(op.f("ck_audit_events_event_type"), "audit_events", type_="check")
    op.create_check_constraint("event_type", "audit_events",
        "event_type IN (" + ",".join("'" + value + "'" for value in OLD_EVENTS) + ")")
