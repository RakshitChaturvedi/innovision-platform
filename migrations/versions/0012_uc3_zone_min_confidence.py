"""Add min_confidence column to uc3_zones and zones

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-11
"""

revision = "0012"
down_revision = "0011"

import sqlalchemy as sa
from alembic import op

def upgrade():
    # 1. Add min_confidence to uc3_zones table
    op.add_column(
        "uc3_zones",
        sa.Column("min_confidence", sa.Float, nullable=False, server_default="0.50"),
    )

    # 2. Add min_confidence to zones table
    op.add_column(
        "zones",
        sa.Column("min_confidence", sa.Float, nullable=False, server_default="0.50"),
    )

def downgrade():
    op.drop_column("zones", "min_confidence")
    op.drop_column("uc3_zones", "min_confidence")
