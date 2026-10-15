"""Add product storage locations.

Revision ID: 0007_shelf_metadata
Revises: 0006_counter_indexes
"""
from alembic import op


revision = "0007_shelf_metadata"
down_revision = "0006_counter_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS storage_section VARCHAR(100) NOT NULL DEFAULT 'General'")
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS shelf_number VARCHAR(50) NOT NULL DEFAULT 'Unassigned'")


def downgrade() -> None:
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS shelf_number")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS storage_section")