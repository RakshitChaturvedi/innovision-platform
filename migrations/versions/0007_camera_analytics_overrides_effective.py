revision = "0007"
down_revision = "0006"

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from alembic import op

def upgrade():
    # 1. Create camera_analytics_overrides Table
    op.create_table(
        "camera_analytics_overrides",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("camera_id", UUID, sa.ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analytic_id", UUID, sa.ForeignKey("analytics_catalog.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("camera_id", "analytic_id", name="uq_camera_analytic_override"),
    )
    op.create_index("idx_camera_overrides_camera_analytic", "camera_analytics_overrides", ["camera_id", "analytic_id"])
    op.create_index("idx_camera_overrides_analytic_enabled", "camera_analytics_overrides", ["analytic_id", "is_enabled"])

    # 2. Create camera_effective_analytics Table
    op.create_table(
        "camera_effective_analytics",
        sa.Column("camera_id", UUID, sa.ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analytic_id", UUID, sa.ForeignKey("analytics_catalog.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("effective_config", JSONB, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("camera_id", "analytic_id", name="pk_camera_effective_analytics"),
    )
    op.create_index("idx_effective_analytic_active", "camera_effective_analytics", ["analytic_id", "is_active"])
    op.create_index("idx_effective_camera_active", "camera_effective_analytics", ["camera_id", "is_active"])

    # 3. Backfill legacy camera active use_cases into camera_effective_analytics for existing cameras
    op.execute("""
        INSERT INTO camera_effective_analytics (camera_id, analytic_id, is_active, updated_at)
        SELECT 
            c.id AS camera_id,
            a.id AS analytic_id,
            true AS is_active,
            now() AS updated_at
        FROM cameras c
        JOIN analytics_catalog a ON a.internal_code = ANY(c.use_cases) OR a.code = ANY(c.use_cases)
        ON CONFLICT (camera_id, analytic_id) DO UPDATE SET is_active = true, updated_at = now();
    """)

def downgrade():
    op.drop_index("idx_effective_camera_active", "camera_effective_analytics")
    op.drop_index("idx_effective_analytic_active", "camera_effective_analytics")
    op.drop_table("camera_effective_analytics")

    op.drop_index("idx_camera_overrides_analytic_enabled", "camera_analytics_overrides")
    op.drop_index("idx_camera_overrides_camera_analytic", "camera_analytics_overrides")
    op.drop_table("camera_analytics_overrides")
