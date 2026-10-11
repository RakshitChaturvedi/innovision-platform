revision = "0004"
down_revision = "0003"

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, ENUM
from alembic import op

def upgrade():
    # 1. Create Organizations Table
    op.create_table(
        "organizations",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(100), nullable=False, unique=True),
        sa.Column("tier", sa.String(50), nullable=False, server_default="enterprise"),
        sa.Column("timezone", sa.String(100), nullable=False, server_default="UTC"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_organizations_code", "organizations", ["code"])

    # 2. Create Sites Table
    op.create_table(
        "sites",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("timezone", sa.String(100), nullable=False, server_default="UTC"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", "code", name="uq_sites_org_code"),
    )
    op.create_index("idx_sites_organization", "sites", ["organization_id"])

    # 3. Create Zones Table
    op.create_table(
        "zones",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("site_id", UUID, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False, server_default="Default Zone"),
        sa.Column("slug", sa.String(100), nullable=False, server_default="default-zone"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("zone_type", sa.String(100), nullable=False, server_default="general"),
        sa.Column("risk_level", sa.String(50), nullable=False, server_default="medium"),
        sa.Column("required_ppe", ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_zones_site", "zones", ["site_id"])

    # 4. Camera Lifecycle Enum Type
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE camera_lifecycle_enum AS ENUM ('onboarding', 'unassigned', 'active', 'disabled', 'offline');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # 5. Extend Existing Cameras Table with Hierarchy and Lifecycle Fields
    op.add_column("cameras", sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True))
    op.add_column("cameras", sa.Column("site_id", UUID, sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True))
    op.add_column("cameras", sa.Column("zone_id", UUID, sa.ForeignKey("zones.id", ondelete="SET NULL"), nullable=True))
    op.add_column("cameras", sa.Column("lifecycle_state", sa.Enum('onboarding', 'unassigned', 'active', 'disabled', 'offline', name='camera_lifecycle_enum', create_type=False), nullable=False, server_default="unassigned"))
    op.add_column("cameras", sa.Column("source_type", sa.String(50), nullable=False, server_default="rtsp"))
    op.add_column("cameras", sa.Column("source_url", sa.String(1024), nullable=True))
    op.add_column("cameras", sa.Column("is_simulation", sa.Boolean, nullable=False, server_default="false"))

    op.create_index("idx_cameras_organization", "cameras", ["organization_id"])
    op.create_index("idx_cameras_site", "cameras", ["site_id"])
    op.create_index("idx_cameras_zone", "cameras", ["zone_id"])
    op.create_index("idx_cameras_lifecycle", "cameras", ["lifecycle_state"])

def downgrade():
    op.drop_index("idx_cameras_lifecycle", "cameras")
    op.drop_index("idx_cameras_site", "cameras")
    op.drop_index("idx_cameras_organization", "cameras")

    op.drop_column("cameras", "is_simulation")
    op.drop_column("cameras", "source_url")
    op.drop_column("cameras", "source_type")
    op.drop_column("cameras", "lifecycle_state")
    op.drop_column("cameras", "site_id")
    op.drop_column("cameras", "organization_id")

    op.execute("DROP TYPE IF EXISTS camera_lifecycle_enum")

    op.drop_index("idx_zones_site", "zones")
    op.drop_column("zones", "risk_level")
    op.drop_column("zones", "zone_type")
    op.drop_column("zones", "site_id")

    op.drop_table("sites")
    op.drop_table("organizations")
