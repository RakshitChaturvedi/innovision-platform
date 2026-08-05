revision = "0001"
down_revision = None

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from alembic import op

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TYPE camera_status AS ENUM ('online', 'offline', 'reconnecting', 'disabled')
    """)
    op.execute("""
        CREATE TYPE alert_severity AS ENUM ('low', 'medium', 'high', 'critical')
    """)
    op.execute("""
        CREATE TYPE alert_status AS ENUM ('pending', 'acknowledged', 'in_progress', 'resolved', 'closed')
    """)
    op.execute("""
        CREATE TYPE incident_status AS ENUM ('active', 'acknowledged', 'in_progress', 'resolved', 'closed')
    """)
    op.execute("""
        CREATE TYPE operator_role AS ENUM ('superadmin', 'admin', 'operator', 'viewer')
    """)
    op.execute("""
        CREATE TYPE source_uc AS ENUM ('uc1', 'uc2', 'uc3', 'uc4')
    """)

    op.create_table(
        "cameras",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("rtsp_url", sa.String(1024), nullable=True),
        sa.Column("status",
                  sa.Enum("online", "offline", "reconnecting", "disabled",
                          name="camera_status"),
                  nullable=False, server_default="offline"),
        sa.Column("use_cases", ARRAY(sa.String), nullable=False,
                  server_default="{}"),
        sa.Column("fps", sa.Integer, nullable=False, server_default="10"),
        sa.Column("metadata", JSONB, nullable=False,
                  server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_cameras_status", "cameras", ["status"]) 

    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role",
                  sa.Enum("superadmin", "admin", "operator", "viewer",
                          name="operator_role"),
                  nullable=False, server_default="operator"),
        sa.Column("camera_ids", ARRAY(UUID), nullable=False,
                  server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_users_email", "users", ["email"])

    op.create_table(
        "sessions",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", UUID,
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("refresh_token_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_sessions_user", "sessions", ["user_id"])
    op.create_index("idx_sessions_expires", "sessions", ["expires_at"])

    op.create_table(
        "alerts",
        sa.Column("id", UUID, primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("alert_id", UUID, nullable=False, unique=True),
        sa.Column("camera_id", UUID,
                  sa.ForeignKey("cameras.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("source_uc",
                  sa.Enum("uc1", "uc2", "uc3", "uc4", name="source_uc"),
                  nullable=False),
        sa.Column("alert_type", sa.String(100), nullable=False),
        sa.Column("severity",
                  sa.Enum("low", "medium", "high", "critical",
                          name="alert_severity"),
                  nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("source_event_id", UUID, nullable=False),
        sa.Column("frame_reference", sa.String(512), nullable=True),
        sa.Column("frame_provider", sa.String(50), nullable=True),
        sa.Column("status",
                  sa.Enum("pending", "acknowledged", "in_progress",
                          "resolved", "closed", name="alert_status"),
                  nullable=False, server_default="pending"),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", UUID,
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", UUID,
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
    )
    op.create_index("idx_alerts_camera_time", "alerts", ["camera_id", "created_at"])
    op.create_index("idx_alerts_status", "alerts", ["status"])
    op.create_index("idx_alerts_source_uc", "alerts", ["source_uc"])
    op.create_index("idx_alerts_severity", "alerts", ["severity"])
    op.create_index("idx_alerts_alert_id", "alerts", ["alert_id"])

    op.create_table(
        "incidents",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("alert_id", UUID, sa.ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status",
                  sa.Enum("active", "acknowledged", "in_progress", "resolved", "closed", name="incident_status"),
                  nullable=False, server_default="active"),
        sa.Column("assigned_to", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_incidents_status", "incidents", ["status"])
    op.create_index("idx_incidents_alert", "incidents", ["alert_id"])

    op.create_table(
        "incident_timeline",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("incident_id", UUID, sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("from_status", sa.String(50), nullable=True),
        sa.Column("to_status", sa.String(50), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.create_index("idx_incident_timeline_incident", "incident_timeline", ["incident_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("service", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(255), nullable=False),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("source_uc", sa.Enum("uc1", "uc2", "uc3", "uc4", name="source_uc"), nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))

    # append only rules enforced at db level
    op.execute("""CREATE RULE audit_log_no_update AS ON UPDATE TO audit_log DO INSTEAD NOTHING""")
    op.execute("""CREATE RULE audit_log_no_delete AS ON DELETE TO audit_log DO INSTEAD NOTHING""")
    op.create_index("idx_audit_service_time", "audit_log", ["service", "timestamp"])
    op.create_index("idx_audit_entity", "audit_log", ["entity_type", "entity_id"])

    # notification log
    op.create_table(
        "notification_log",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("alert_id", UUID, sa.ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", UUID, sa.ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    )

    #seed
    op.execute("""
    INSERT INTO cameras (id, name, location, status, profile, use_cases)
    VALUES
        ('00000000-0000-0000-0000-000000000001',
            'Test Camera UC1', 'Integration Test', 'online', 'balanced',
            ARRAY['uc1']),
        ('00000000-0000-0000-0000-000000000002',
            'Test Camera UC2', 'Integration Test', 'online', 'balanced',
            ARRAY['uc2']),
        ('00000000-0000-0000-0000-000000000003',
            'Test Camera UC3', 'Integration Test', 'online', 'balanced',
            ARRAY['uc3']),
        ('00000000-0000-0000-0000-000000000004',
            'Test Camera UC4', 'Integration Test', 'online', 'balanced',
            ARRAY['uc4'])
    ON CONFLICT DO NOTHING
""")

    op.execute("""
    INSERT INTO users (id, name, email, password_hash, role, camera_ids)
    VALUES (
        'ffffffff-ffff-ffff-ffff-ffffffffffff',
        'Platform Admin',
        'admin@innovision.com',
        '$2b$12$placeholder_hash_change_in_production',
        'superadmin',
        ARRAY[
            '00000000-0000-0000-0000-000000000001'::uuid,
            '00000000-0000-0000-0000-000000000002'::uuid,
            '00000000-0000-0000-0000-000000000003'::uuid,
            '00000000-0000-0000-0000-000000000004'::uuid
        ]
    )
    ON CONFLICT DO NOTHING
""")

def downgrade():
    op.drop_table("notification_log")
    op.drop_table("audit_log")
    op.drop_table("incident_timeline")
    op.drop_table("incidents")
    op.drop_table("alerts")
    op.drop_table("sessions")
    op.drop_table("users")
    op.drop_table("cameras")

    for enum in ["source_uc", "operator_role", "incident_status", 
                 "alert_status", "alert_severity", "camera_status"]:
        op.execute(f"DROP TYPE IF EXISTS {enum}")