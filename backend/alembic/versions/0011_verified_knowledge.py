"""Verified knowledge backed by existing approval ledger."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "0011_verified_knowledge"
down_revision = "0010_phase5f_repairs"
branch_labels = None
depends_on = None

_OLD_EVENTS = ('GOVERNED_REVISION_CREATED', 'LOGIN_SUCCESS', 'LOGIN_FAILURE', 'APPROVAL_DECISION_APPROVE', 'APPROVAL_DECISION_REJECT', 'APPROVAL_DECISION_REVOKE', 'APPROVAL_AUTHORIZATION_DENIED', 'ADVISORY_RELEASE_SUCCESS', 'ADVISORY_RELEASE_DENIED', 'EVIDENCE_MANIFEST_CREATED', 'EVIDENCE_INTEGRITY_VERIFIED', 'EVIDENCE_INTEGRITY_FAILED', 'PREFLIGHT_OUT_OF_SCOPE_REFUSED', 'PREFLIGHT_INJECTION_REFUSED', 'PREFLIGHT_UNSAFE_ACTION_REFUSED', 'PREFLIGHT_SCOPE_DENIED', 'PREFLIGHT_CLARIFICATION_REQUIRED')
_NEW_EVENTS = _OLD_EVENTS + ('KNOWLEDGE_CANDIDATE_CREATED', 'KNOWLEDGE_VERIFIED', 'KNOWLEDGE_STALE', 'KNOWLEDGE_REVOKED', 'VERIFIED_KNOWLEDGE_SERVED')

def _events(values):
    op.execute("ALTER TABLE audit_events DROP CONSTRAINT ck_audit_events_event_type")
    op.execute("ALTER TABLE audit_events ADD CONSTRAINT ck_audit_events_event_type CHECK (event_type IN (" + ",".join("'"+v+"'" for v in values) + "))")

def upgrade():
    _events(_NEW_EVENTS)
    op.create_table("verified_knowledge",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("match_key", sa.String(64), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("source_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("access_scope", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), sa.ForeignKey("verified_knowledge.id")),
        sa.Column("approval_revision_id", sa.Uuid(), sa.ForeignKey("action_revisions.id"), nullable=False, unique=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("verified_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('CANDIDATE','VERIFIED','STALE','REVOKED')", name="knowledge_status"))
    op.create_index("ix_verified_knowledge_match_key", "verified_knowledge", ["match_key"])
    op.create_index("ix_verified_knowledge_status", "verified_knowledge", ["status"])

def downgrade():
    # Existing immutable A1 audit events deliberately prevent a destructive downgrade.
    _events(_OLD_EVENTS)
    op.drop_table("verified_knowledge")
