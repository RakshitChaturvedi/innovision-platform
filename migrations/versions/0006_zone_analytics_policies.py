revision = "0006"
down_revision = "0005"

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

def upgrade():
    # Create zone_analytics_policies Table
    op.create_table(
        "zone_analytics_policies",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("zone_id", UUID, sa.ForeignKey("zones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analytic_id", UUID, sa.ForeignKey("analytics_catalog.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("zone_id", "analytic_id", name="uq_zone_analytic_policy"),
    )
    op.create_index("idx_zone_policies_zone_enabled", "zone_analytics_policies", ["zone_id", "is_enabled"])
    op.create_index("idx_zone_policies_analytic_enabled", "zone_analytics_policies", ["analytic_id", "is_enabled"])

def downgrade():
    op.drop_index("idx_zone_policies_analytic_enabled", "zone_analytics_policies")
    op.drop_index("idx_zone_policies_zone_enabled", "zone_analytics_policies")
    op.drop_table("zone_analytics_policies")
