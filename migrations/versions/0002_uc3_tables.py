revision = "0002"
down_revision = "0001"

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from alembic import op

def upgrade():
    # 1. UC3 Events Table (BaseAnalyticsEvent contract)
    op.create_table(
        "uc3_events",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("organization_id", UUID, nullable=True),
        sa.Column("camera_id", UUID, sa.ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone_id", UUID, nullable=True),
        sa.Column("track_id", sa.Integer, nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False, server_default="ppe_detected"),
        sa.Column("missing_ppe", ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("present_ppe", ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("compliance_score", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("frame_reference", sa.String(512), nullable=True),
        sa.Column("frame_provider", sa.String(50), nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("idx_uc3_events_camera_time", "uc3_events", ["camera_id", "timestamp"])
    op.create_index("idx_uc3_events_event_type", "uc3_events", ["event_type"])

    # 2. UC3 Zones Table
    op.create_table(
        "uc3_zones",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("organization_id", UUID, nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("risk_level", sa.String(50), nullable=False, server_default="medium"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # 3. UC3 Zone PPE Rules Table
    op.create_table(
        "uc3_zone_ppe_rules",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("zone_id", UUID, sa.ForeignKey("uc3_zones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ppe_type", sa.String(50), nullable=False),
        sa.Column("required", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("severity", sa.String(50), nullable=False, server_default="high"),
        sa.Column("grace_seconds", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("idx_uc3_zone_rules_zone", "uc3_zone_ppe_rules", ["zone_id"])

    # 4. Reports Table (Fixes platform reporting worker missing table bug)
    op.create_table(
        "reports",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("organization_id", UUID, nullable=True),
        sa.Column("report_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("download_url", sa.String(1024), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_reports_status", "reports", ["status"])

def downgrade():
    op.drop_table("reports")
    op.drop_table("uc3_zone_ppe_rules")
    op.drop_table("uc3_zones")
    op.drop_table("uc3_events")
