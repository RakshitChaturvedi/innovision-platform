revision = "0008"
down_revision = "0007"

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

def upgrade():
    # 1. Add organization_id and is_active to users table
    op.add_column(
        "users",
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true")
    )
    op.create_index("idx_users_organization", "users", ["organization_id"])
    op.create_index("idx_users_is_active", "users", ["is_active"])

    # 2. Add 'org_admin' value to operator_role Enum type in Postgres if absent
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE operator_role ADD VALUE IF NOT EXISTS 'org_admin';
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

def downgrade():
    op.drop_index("idx_users_is_active", "users")
    op.drop_index("idx_users_organization", "users")
    op.drop_column("users", "is_active")
    op.drop_column("users", "organization_id")
