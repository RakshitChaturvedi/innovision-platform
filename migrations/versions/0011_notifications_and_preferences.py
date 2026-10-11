revision = "0011"
down_revision = "0010"

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from alembic import op

def upgrade():
    # 1. Create notifications table
    op.create_table(
        "notifications",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("recipient_user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("severity", sa.String(50), nullable=False, server_default="medium"),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_notifications_recipient", "notifications", ["recipient_user_id", "created_at"])
    op.create_index("idx_notifications_unread", "notifications", ["recipient_user_id", "is_read"])
    op.create_index("idx_notifications_organization", "notifications", ["organization_id"])

    # 2. Create notification_preferences table
    op.create_table(
        "notification_preferences",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("notification_type", sa.String(100), nullable=False),
        sa.Column("in_app_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("email_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "notification_type", name="uq_notification_user_pref"),
    )
    op.create_index("idx_notification_pref_user", "notification_preferences", ["user_id"])

def downgrade():
    op.drop_index("idx_notification_pref_user", "notification_preferences")
    op.drop_table("notification_preferences")

    op.drop_index("idx_notifications_organization", "notifications")
    op.drop_index("idx_notifications_unread", "notifications")
    op.drop_index("idx_notifications_recipient", "notifications")
    op.drop_table("notifications")
