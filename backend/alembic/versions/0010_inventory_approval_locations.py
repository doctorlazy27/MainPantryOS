"""Defer inventory batch assignment and add aisle locations.

Revision ID: 0010_inventory_approval_locations
Revises: 0009_legacy_email_compatibility
"""
from alembic import op


revision = "0010_approval_locations"
down_revision = "0009_legacy_email_compatibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE inventory_addition_requests ALTER COLUMN batch_id DROP NOT NULL")
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS aisle VARCHAR(50) NOT NULL DEFAULT 'Unassigned'")


def downgrade() -> None:
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS aisle")