"""Add isolated UC2 detection and evidence backup table

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-04 22:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "uc2_detection_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("alert_id", UUID(as_uuid=True), nullable=True),
        sa.Column("camera_id", UUID(as_uuid=True), nullable=True),
        sa.Column("detection_type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("verification_score", sa.Float, nullable=True),
        sa.Column("bbox_x1", sa.Integer, nullable=True),
        sa.Column("bbox_y1", sa.Integer, nullable=True),
        sa.Column("bbox_x2", sa.Integer, nullable=True),
        sa.Column("bbox_y2", sa.Integer, nullable=True),
        sa.Column("area", sa.Integer, nullable=True),
        sa.Column("area_percentage", sa.Float, nullable=True),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="rtsp"),
        sa.Column("frame_seq", sa.Integer, nullable=True),
        sa.Column("evidence_key", sa.String(512), nullable=True),
        sa.Column("evidence_bucket", sa.String(128), nullable=False, server_default="innovision-evidence"),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_uc2_events_alert_id", "uc2_detection_events", ["alert_id"], if_not_exists=True)
    op.create_index("idx_uc2_events_camera_time", "uc2_detection_events", ["camera_id", "created_at"], if_not_exists=True)
    op.create_index("idx_uc2_events_type_time", "uc2_detection_events", ["detection_type", "created_at"], if_not_exists=True)

def downgrade():
    op.drop_table("uc2_detection_events")
