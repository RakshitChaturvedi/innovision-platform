"""Drop obsolete uc3_compliance_events table

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS uc3_compliance_events CASCADE")

def downgrade() -> None:
    pass
