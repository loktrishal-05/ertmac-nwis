"""Phase 4B agent-run tracing tables. No Phase 0-3C table is touched."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_agent_runs"
down_revision = "0003_structured_data"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=True),
        sa.Column("route", sa.String(50), nullable=True),
        sa.Column("route_confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("runtime", sa.String(50), nullable=True),
        sa.Column("gateway_repair_attempts", sa.Integer(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
    )
    op.create_index("ix_agent_runs_route", "agent_runs", ["route"])

    op.create_table(
        "agent_run_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("node_name", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("tool_name", sa.String(100), nullable=True),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("usage", postgresql.JSONB(), nullable=False),
        sa.Column("timings", postgresql.JSONB(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], name="fk_agent_run_steps_run_id_agent_runs"),
        sa.PrimaryKeyConstraint("id", name="pk_agent_run_steps"),
    )
    op.create_index("ix_agent_run_steps_run_id", "agent_run_steps", ["run_id"])


def downgrade():
    op.drop_index("ix_agent_run_steps_run_id", table_name="agent_run_steps")
    op.drop_table("agent_run_steps")
    op.drop_index("ix_agent_runs_route", table_name="agent_runs")
    op.drop_table("agent_runs")
