"""Phase 5E: widen audit_events.event_type to admit the five deterministic
pre-routing preflight event types. No new table -- the preflight gate
(app.services.preflight) is a pure computation with no persisted domain
object of its own; only its audit trail needs schema changes."""
from alembic import op

revision = "0009_phase5e_preflight"
down_revision = "0008_phase5d_evidence_integrity"
branch_labels = None
depends_on = None

_OLD_EVENT_TYPES = (
    "GOVERNED_REVISION_CREATED", "LOGIN_SUCCESS", "LOGIN_FAILURE",
    "APPROVAL_DECISION_APPROVE", "APPROVAL_DECISION_REJECT", "APPROVAL_DECISION_REVOKE",
    "APPROVAL_AUTHORIZATION_DENIED", "ADVISORY_RELEASE_SUCCESS", "ADVISORY_RELEASE_DENIED",
    "EVIDENCE_MANIFEST_CREATED", "EVIDENCE_INTEGRITY_VERIFIED", "EVIDENCE_INTEGRITY_FAILED",
)
_NEW_EVENT_TYPES = _OLD_EVENT_TYPES + (
    "PREFLIGHT_OUT_OF_SCOPE_REFUSED", "PREFLIGHT_INJECTION_REFUSED",
    "PREFLIGHT_UNSAFE_ACTION_REFUSED", "PREFLIGHT_SCOPE_DENIED", "PREFLIGHT_CLARIFICATION_REQUIRED",
)


def upgrade():
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
