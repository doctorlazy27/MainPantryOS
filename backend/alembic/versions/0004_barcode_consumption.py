"""Track remaining units for barcode stock reduction.

Revision ID: 0004_barcode_consumption
Revises: d7246e2552b9
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0004_barcode_consumption"
down_revision: Union[str, Sequence[str], None] = "d7246e2552b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE boxed_units ADD COLUMN IF NOT EXISTS remaining_units INTEGER NOT NULL DEFAULT 0")
    op.execute("UPDATE boxed_units SET remaining_units = units WHERE remaining_units = 0 AND units > 0")


def downgrade() -> None:
    op.execute("ALTER TABLE boxed_units DROP COLUMN IF EXISTS remaining_units")