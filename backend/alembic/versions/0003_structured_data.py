"""Phase 3C maintenance/sensor structured data tables and sensor_readings provenance columns."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_structured_data"
down_revision = "0002_document_versions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "structured_data_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("rejected_row_count", sa.Integer(), nullable=False),
        sa.Column("ingestion_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_structured_data_sources"),
        sa.UniqueConstraint("source_sha256", name="uq_structured_data_sources_source_sha256"),
    )

    op.create_table(
        "maintenance_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("equipment_id", sa.Uuid(), nullable=False),
        sa.Column("raw_equipment_tag", sa.String(100), nullable=False),
        sa.Column("work_order_id", sa.String(100), nullable=True),
        sa.Column("maintenance_type", sa.String(50), nullable=True),
        sa.Column("failure_mode", sa.String(255), nullable=True),
        sa.Column("maintenance_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("downtime_hours", sa.Float(), nullable=True),
        sa.Column("parts_replaced", sa.Text(), nullable=True),
        sa.Column("technician_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("raw_row", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], name="fk_maintenance_records_equipment_id_equipment"),
        sa.PrimaryKeyConstraint("id", name="pk_maintenance_records"),
        sa.UniqueConstraint("source_sha256", "source_row_number", name="uq_maintenance_records_source_row"),
    )
    op.create_index("ix_maintenance_records_equipment_id", "maintenance_records", ["equipment_id"])
    op.create_index("ix_maintenance_records_work_order_id", "maintenance_records", ["work_order_id"])
    op.create_index("ix_maintenance_records_maintenance_date", "maintenance_records", ["maintenance_date"])
    op.create_index("ix_maintenance_records_source_sha256", "maintenance_records", ["source_sha256"])

    op.add_column("sensor_readings", sa.Column("sensor_tag", sa.String(100), nullable=False, server_default="unknown"))
    op.alter_column("sensor_readings", "sensor_tag", server_default=None)
    op.add_column("sensor_readings", sa.Column("quality", sa.String(20), nullable=True))
    op.add_column("sensor_readings", sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False,
    ))
    op.add_column("sensor_readings", sa.Column("source_filename", sa.String(255), nullable=False, server_default="unknown"))
    op.alter_column("sensor_readings", "source_filename", server_default=None)
    op.add_column("sensor_readings", sa.Column("source_sha256", sa.String(64), nullable=False, server_default="0" * 64))
    op.alter_column("sensor_readings", "source_sha256", server_default=None)
    op.add_column("sensor_readings", sa.Column("source_row_number", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("sensor_readings", "source_row_number", server_default=None)
    op.alter_column("sensor_readings", "unit", nullable=True)
    op.create_index("ix_sensor_readings_sensor_tag", "sensor_readings", ["sensor_tag"])
    op.create_index("ix_sensor_readings_source_sha256", "sensor_readings", ["source_sha256"])
    op.create_unique_constraint(
        "uq_sensor_readings_source_row", "sensor_readings", ["source_sha256", "source_row_number"],
    )


def downgrade():
    op.drop_constraint("uq_sensor_readings_source_row", "sensor_readings", type_="unique")
    op.drop_index("ix_sensor_readings_source_sha256", table_name="sensor_readings")
    op.drop_index("ix_sensor_readings_sensor_tag", table_name="sensor_readings")
    op.alter_column("sensor_readings", "unit", nullable=False)
    op.drop_column("sensor_readings", "source_row_number")
    op.drop_column("sensor_readings", "source_sha256")
    op.drop_column("sensor_readings", "source_filename")
    op.drop_column("sensor_readings", "created_at")
    op.drop_column("sensor_readings", "quality")
    op.drop_column("sensor_readings", "sensor_tag")

    op.drop_index("ix_maintenance_records_source_sha256", table_name="maintenance_records")
    op.drop_index("ix_maintenance_records_maintenance_date", table_name="maintenance_records")
    op.drop_index("ix_maintenance_records_work_order_id", table_name="maintenance_records")
    op.drop_index("ix_maintenance_records_equipment_id", table_name="maintenance_records")
    op.drop_table("maintenance_records")

    op.drop_table("structured_data_sources")
