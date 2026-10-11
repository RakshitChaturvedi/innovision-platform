revision = "0005"
down_revision = "0004"

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

def upgrade():
    # 1. Create analytics_catalog Table
    op.create_table(
        "analytics_catalog",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("code", sa.String(100), nullable=False, unique=True),
        sa.Column("internal_code", sa.String(50), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(100), nullable=False, server_default="general"),
        sa.Column("icon_key", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_analytics_catalog_code", "analytics_catalog", ["code"])
    op.create_index("idx_analytics_catalog_internal", "analytics_catalog", ["internal_code"])

    # Seed the 4 initial platform analytics
    op.execute("""
        INSERT INTO analytics_catalog (id, code, internal_code, display_name, description, category, icon_key, is_active)
        VALUES
        ('11111111-1111-1111-1111-111111111111', 'intrusion_detection', 'uc1', 'Intrusion & Perimeter Detection', 'Perimeter security, zone intrusion detection, restricted entry, and crowd density monitoring.', 'security', 'shield-alert', true),
        ('22222222-2222-2222-2222-222222222222', 'fire_smoke_detection', 'uc2', 'Fire & Smoke Detection', 'Early thermal anomaly, fire, and smoke detection in industrial environments.', 'safety', 'flame', true),
        ('33333333-3333-3333-3333-333333333333', 'ppe_detection', 'uc3', 'PPE Detection', 'Personal Protective Equipment (helmet, vest, mask, gloves) compliance monitoring.', 'safety', 'hard-hat', true),
        ('44444444-4444-4444-4444-444444444444', 'anpr_speed_detection', 'uc4', 'ANPR & Speed Detection', 'Automatic Number Plate Recognition, speed estimation, and vehicle authorization monitoring.', 'traffic', 'car', true)
        ON CONFLICT (code) DO NOTHING;
    """)

    # 2. Create organization_subscriptions Table
    op.create_table(
        "organization_subscriptions",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analytic_id", UUID, sa.ForeignKey("analytics_catalog.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("max_cameras_allowed", sa.Integer, nullable=False, server_default="20"),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", "analytic_id", name="uq_org_subscription_analytic"),
    )
    op.create_index("idx_org_subscriptions_org", "organization_subscriptions", ["organization_id"])
    op.create_index("idx_org_subscriptions_analytic", "organization_subscriptions", ["analytic_id"])

def downgrade():
    op.drop_index("idx_org_subscriptions_analytic", "organization_subscriptions")
    op.drop_index("idx_org_subscriptions_org", "organization_subscriptions")
    op.drop_table("organization_subscriptions")

    op.drop_index("idx_analytics_catalog_internal", "analytics_catalog")
    op.drop_index("idx_analytics_catalog_code", "analytics_catalog")
    op.drop_table("analytics_catalog")
