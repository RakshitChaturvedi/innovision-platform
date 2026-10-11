revision = "0010"
down_revision = "0009"

import sqlalchemy as sa
from alembic import op

def upgrade():
    # Add timezone column to organizations if missing
    op.execute("""
        ALTER TABLE organizations
        ADD COLUMN IF NOT EXISTS timezone VARCHAR(100) NOT NULL DEFAULT 'UTC'
    """)

    # Performance indexes for audit querying
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log (user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log (action)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log (timestamp DESC)
    """)

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_audit_timestamp")
    op.execute("DROP INDEX IF EXISTS idx_audit_action")
    op.execute("DROP INDEX IF EXISTS idx_audit_user")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS timezone")
