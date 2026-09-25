"""Bounded CAG packs; trust remains in the A1 registry and approval ledger."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "0012_knowledge_packs"
down_revision = "0011_verified_knowledge"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("knowledge_packs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("match_key", sa.String(64), nullable=False),
        sa.Column("knowledge_id", sa.Uuid(), sa.ForeignKey("verified_knowledge.id"), unique=True, nullable=False),
        sa.Column("members", postgresql.JSONB(), nullable=False))
    op.create_index("ix_knowledge_packs_match_key", "knowledge_packs", ["match_key"])

def downgrade():
    op.drop_table("knowledge_packs")
