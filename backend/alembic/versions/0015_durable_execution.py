"""Durable graph checkpoints, pending writes, and execution receipts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_durable_execution"
down_revision = "0014_product_integration"
branch_labels = None
depends_on = None


def upgrade():
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table("durable_executions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request", json_type, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("current_node", sa.String(100)),
        sa.Column("retry_class", sa.String(40)),
        sa.Column("resume_count", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("checkpoint_version", sa.Integer(), nullable=False),
        sa.Column("interruption_reason", sa.String(100)),
        sa.Column("resume_reason", sa.String(100)),
        sa.Column("selected_model", sa.String(200), nullable=False),
        sa.Column("execution_path", sa.String(60), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("graph_checkpoints",
        sa.Column("execution_id", sa.Uuid(), sa.ForeignKey("durable_executions.id"), primary_key=True),
        sa.Column("namespace", sa.String(200), primary_key=True),
        sa.Column("checkpoint_id", sa.String(100), primary_key=True),
        sa.Column("parent_id", sa.String(100)),
        sa.Column("checkpoint", json_type, nullable=False),
        sa.Column("meta", json_type, nullable=False))
    op.create_table("graph_writes",
        sa.Column("execution_id", sa.Uuid(), sa.ForeignKey("durable_executions.id"), primary_key=True),
        sa.Column("namespace", sa.String(200), primary_key=True),
        sa.Column("checkpoint_id", sa.String(100), primary_key=True),
        sa.Column("task_id", sa.String(100), primary_key=True),
        sa.Column("idx", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(200), nullable=False),
        sa.Column("value", json_type, nullable=False))
    op.create_table("execution_operations",
        sa.Column("execution_id", sa.Uuid(), sa.ForeignKey("durable_executions.id"), primary_key=True),
        sa.Column("key", sa.String(200), primary_key=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("retry_class", sa.String(40)),
        sa.Column("result", json_type),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_table("execution_operations")
    op.drop_table("graph_writes")
    op.drop_table("graph_checkpoints")
    op.drop_table("durable_executions")
