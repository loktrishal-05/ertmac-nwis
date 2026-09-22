"""Phase 5F repair: block TRUNCATE on the audit tables.

The Phase 5C row-level immutability triggers (BEFORE UPDATE OR DELETE) do
not fire on TRUNCATE -- a statement-level operation that bypasses row
triggers entirely. This adds a BEFORE TRUNCATE ... FOR EACH STATEMENT
trigger reusing the existing reject_audit_event_mutation() function
(created in 0007, never dropped), consistent with the same immutability
strategy already established for UPDATE/DELETE. This does not defend
against a role with privileges to disable the trigger first (documented
limitation, same as Phase 5C's own "tamper-evident, not tamper-proof"
posture) -- app.services.audit.verify_chain's chain-head comparison
(docs/phase5f-validation.md H3) is the second, independent layer that
still detects an empty-but-should-have-events chain even if this trigger
is bypassed."""
from alembic import op

revision = "0010_phase5f_repairs"
down_revision = "0009_phase5e_preflight"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("audit_events", "audit_checkpoints"):
        op.execute(
            f"CREATE TRIGGER truncate_protect_{table} BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_event_mutation()"
        )


def downgrade():
    for table in ("audit_checkpoints", "audit_events"):
        op.execute(f"DROP TRIGGER truncate_protect_{table} ON {table}")
