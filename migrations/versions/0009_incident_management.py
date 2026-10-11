revision = "0009"
down_revision = "0008"

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

def upgrade():
    op.execute("ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'open'")
    op.execute("ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'investigating'")

    # 1. Add fields to incidents table
    op.add_column(
        "incidents",
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    )
    op.add_column(
        "incidents",
        sa.Column("site_id", UUID, sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)
    )
    op.add_column(
        "incidents",
        sa.Column("zone_id", UUID, sa.ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)
    )
    op.add_column(
        "incidents",
        sa.Column("camera_id", UUID, sa.ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True)
    )
    op.add_column(
        "incidents",
        sa.Column("description", sa.Text, nullable=True)
    )
    op.add_column(
        "incidents",
        sa.Column("severity", sa.String(50), nullable=False, server_default="medium")
    )
    op.add_column(
        "incidents",
        sa.Column("source_type", sa.String(50), nullable=False, server_default="alert")
    )
    op.add_column(
        "incidents",
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    )
    op.add_column(
        "incidents",
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "incidents",
        sa.Column("investigating_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "incidents",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_index("idx_incidents_organization", "incidents", ["organization_id"])
    op.create_index("idx_incidents_site", "incidents", ["site_id"])
    op.create_index("idx_incidents_zone", "incidents", ["zone_id"])
    op.create_index("idx_incidents_camera", "incidents", ["camera_id"])
    op.create_index("idx_incidents_severity", "incidents", ["severity"])
    op.create_index("idx_incidents_created_by", "incidents", ["created_by"])

    # 2. Create incident_alerts junction table (M:N relationship)
    op.create_table(
        "incident_alerts",
        sa.Column("incident_id", UUID, sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_id", UUID, sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("linked_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.PrimaryKeyConstraint("incident_id", "alert_id", name="pk_incident_alerts"),
    )
    op.create_index("idx_incident_alerts_alert", "incident_alerts", ["alert_id"])
    op.create_index("idx_incident_alerts_incident", "incident_alerts", ["incident_id"])

def downgrade():
    op.drop_index("idx_incident_alerts_incident", "incident_alerts")
    op.drop_index("idx_incident_alerts_alert", "incident_alerts")
    op.drop_table("incident_alerts")

    op.drop_index("idx_incidents_created_by", "incidents")
    op.drop_index("idx_incidents_severity", "incidents")
    op.drop_index("idx_incidents_camera", "incidents")
    op.drop_index("idx_incidents_zone", "incidents")
    op.drop_index("idx_incidents_site", "incidents")
    op.drop_index("idx_incidents_organization", "incidents")

    op.drop_column("incidents", "closed_at")
    op.drop_column("incidents", "investigating_at")
    op.drop_column("incidents", "acknowledged_at")
    op.drop_column("incidents", "created_by")
    op.drop_column("incidents", "source_type")
    op.drop_column("incidents", "severity")
    op.drop_column("incidents", "description")
    op.drop_column("incidents", "camera_id")
    op.drop_column("incidents", "zone_id")
    op.drop_column("incidents", "site_id")
    op.drop_column("incidents", "organization_id")
