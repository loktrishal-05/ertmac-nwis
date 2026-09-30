"""Local accounts, bounded recovery and optional connected identities."""
from alembic import op
import sqlalchemy as sa

revision = "0017_accounts_recovery"
down_revision = "0016_enterprise_knowledge"
branch_labels = None
depends_on = None

EVENTS = ("USER_SIGNUP", "SIGNUP_APPROVED", "PASSWORD_RESET_REQUESTED", "PASSWORD_RESET_VERIFIED",
          "PASSWORD_RESET_COMPLETED", "IDENTITY_LINKED", "USER_CREATED", "USER_ACTIVATED",
          "USER_DEACTIVATED", "USER_ROLE_CHANGED", "SESSIONS_REVOKED", "ADMIN_RECOVERY_ISSUED",
          "EMAIL_VERIFICATION_REQUESTED", "EMAIL_VERIFIED", "AUTH_DELIVERY_FAILED")
COLUMNS = ("email", "display_name", "email_verified_at", "is_active", "signup_pending", "password_changed_at",
           "last_login_at", "failed_login_attempts", "locked_until")


def base():
    return [sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]


def owner():
    return sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False)


def expiry():
    return [sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True))]


def upgrade():
    for column in (sa.Column("email", sa.String(254)), sa.Column("display_name", sa.String(100)),
                   sa.Column("email_verified_at", sa.DateTime(timezone=True)),
                   sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
                   sa.Column("signup_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
                   sa.Column("password_changed_at", sa.DateTime(timezone=True)),
                   sa.Column("last_login_at", sa.DateTime(timezone=True)),
                   sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
                   sa.Column("locked_until", sa.DateTime(timezone=True))):
        op.add_column("users", column)
    op.execute("UPDATE users SET display_name = username")
    op.create_index("uq_users_email_normalized", "users", [sa.text("lower(email)")], unique=True)
    op.create_check_constraint("email_normalized", "users", "email IS NULL OR email = lower(trim(email))")
    op.create_table("auth_identities", *base(), owner(),
                    sa.Column("provider", sa.String(20), nullable=False), sa.Column("subject", sa.String(255), nullable=False),
                    sa.UniqueConstraint("provider", "subject"), sa.UniqueConstraint("user_id", "provider"))
    op.create_table("auth_challenges", *base(), owner(),
                    sa.Column("purpose", sa.String(30), nullable=False), sa.Column("code_hash", sa.String(64), nullable=False),
                    *expiry(), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
                    sa.Column("email_delivery", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("auth_reset_capabilities", *base(), owner(),
                    sa.Column("token_hash", sa.String(64), nullable=False, unique=True), *expiry())
    op.create_table("auth_attempts", sa.Column("key", sa.String(64), primary_key=True),
                    sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("auth_oidc_flows", *base(),
                    sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
                    sa.Column("binding_hash", sa.String(64), nullable=False), *expiry())
    for table in ("auth_identities", "auth_challenges", "auth_reset_capabilities"):
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
    for table in ("auth_challenges", "auth_reset_capabilities", "auth_attempts", "auth_oidc_flows"):
        op.create_index(f"ix_{table}_expires_at", table, ["expires_at"])
    event_sql = ",".join("''" + event + "''" for event in EVENTS)
    op.execute("""DO $$ DECLARE old_check text; BEGIN
      SELECT pg_get_constraintdef(oid) INTO old_check FROM pg_constraint
      WHERE conrelid = 'audit_events'::regclass AND conname = 'ck_audit_events_event_type';
      ALTER TABLE audit_events DROP CONSTRAINT ck_audit_events_event_type;
      EXECUTE 'ALTER TABLE audit_events ADD CONSTRAINT ck_audit_events_event_type CHECK ('
        || substring(old_check from 8 for length(old_check)-8)
        || ' OR event_type IN (""" + event_sql + """))';
    END $$""")


def downgrade():
    events = ",".join("'" + event + "'" for event in EVENTS)
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM auth_identities) OR EXISTS (SELECT 1 FROM auth_challenges)
      OR EXISTS (SELECT 1 FROM auth_reset_capabilities) OR EXISTS (SELECT 1 FROM auth_oidc_flows)
      OR EXISTS (SELECT 1 FROM auth_attempts)
      OR EXISTS (SELECT 1 FROM users WHERE email IS NOT NULL OR (display_name IS NOT NULL AND display_name <> username)
                 OR NOT is_active OR signup_pending OR password_changed_at IS NOT NULL
                 OR last_login_at IS NOT NULL OR locked_until IS NOT NULL OR failed_login_attempts <> 0)
      OR EXISTS (SELECT 1 FROM audit_events WHERE event_type IN (""" + events + """)) THEN
        RAISE EXCEPTION 'Account history exists; refusing lossy downgrade';
      END IF;
    END $$""")
    # Removing vocabulary must not rewrite any historical event or its digest.
    op.execute("""DO $$ DECLARE definition text; BEGIN
      SELECT pg_get_constraintdef(oid) INTO definition FROM pg_constraint
      WHERE conrelid = 'audit_events'::regclass AND conname = 'ck_audit_events_event_type';
      ALTER TABLE audit_events DROP CONSTRAINT ck_audit_events_event_type;
      EXECUTE 'ALTER TABLE audit_events ADD CONSTRAINT ck_audit_events_event_type CHECK ('
        || substring(definition from 8 for length(definition)-8)
        || ' AND event_type NOT IN (""" + events.replace("'", "''") + """))';
    END $$""")
    for table in ("auth_oidc_flows", "auth_attempts", "auth_reset_capabilities", "auth_challenges", "auth_identities"):
        op.drop_table(table)
    op.drop_index("uq_users_email_normalized", table_name="users")
    op.drop_constraint(op.f("ck_users_email_normalized"), "users", type_="check")
    for column in reversed(COLUMNS):
        op.drop_column("users", column)
