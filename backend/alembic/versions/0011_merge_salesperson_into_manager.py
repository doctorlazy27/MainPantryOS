"""Merge legacy salesperson accounts into manager role.

Revision ID: 0011_salesperson_to_manager
Revises: 0010_approval_locations
"""

from alembic import op


revision = "0011_salesperson_to_manager"
down_revision = "0010_approval_locations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET role = 'manager' WHERE role = 'salesperson'")


def downgrade() -> None:
    # Existing manager accounts cannot be distinguished from formerly-salesperson accounts.
    pass