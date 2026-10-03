"""Add high-volume production composite indexes for UC2 alerts and incidents

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-01 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade():
    # Composite index for camera hazard deduplication & recent alert history
    op.create_index(
        "idx_alerts_camera_type_time",
        "alerts",
        ["camera_id", "alert_type", "created_at"],
        unique=False,
        if_not_exists=True,
    )
    # Composite index for SOC Dashboard UC2 queries by timestamp
    op.create_index(
        "idx_alerts_uc2_time",
        "alerts",
        ["source_uc", "created_at"],
        unique=False,
        if_not_exists=True,
    )
    # Composite index for active/pending incidents sorted by recency
    op.create_index(
        "idx_incidents_status_time",
        "incidents",
        ["status", "created_at"],
        unique=False,
        if_not_exists=True,
    )

def downgrade():
    op.drop_index("idx_incidents_status_time", table_name="incidents", if_exists=True)
    op.drop_index("idx_alerts_uc2_time", table_name="alerts", if_exists=True)
    op.drop_index("idx_alerts_camera_type_time", table_name="alerts", if_exists=True)
