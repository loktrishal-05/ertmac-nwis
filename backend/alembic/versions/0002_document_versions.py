"""Document revision ingestion state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_document_versions"
down_revision = "0001_phase2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("ingestion_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_document_versions"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name="fk_document_versions_document_id_documents"),
        sa.UniqueConstraint("source_sha256", name="uq_document_versions_source_sha256"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])


def downgrade():
    op.drop_index("ix_document_versions_document_id", table_name="document_versions")
    op.drop_table("document_versions")
