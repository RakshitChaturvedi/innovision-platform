"""Add reports table.

Revision ID: 0002
Revises: 0001
"""
revision = "0002"
down_revision = "0001"

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from alembic import op


def upgrade():
    op.create_table(
        "reports",
        sa.Column(
            "id", UUID, primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "generated_by", UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("report_type", sa.String(100), nullable=True),
        sa.Column("camera_ids", ARRAY(UUID), nullable=False, server_default="{}"),
        sa.Column(
            "date_range_start", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "date_range_end", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "status", sa.String(50), nullable=False, server_default="pending",
        ),
        sa.Column("object_key", sa.String(512), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "completed_at", sa.DateTime(timezone=True), nullable=True,
        ),
    )
    op.create_index("idx_reports_status", "reports", ["status"])
    op.create_index("idx_reports_created", "reports", ["created_at"])


def downgrade():
    op.drop_table("reports")
