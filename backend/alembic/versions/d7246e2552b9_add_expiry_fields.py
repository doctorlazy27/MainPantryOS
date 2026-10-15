"""Add expiry fields

Revision ID: d7246e2552b9
Revises: 0003_legacy_schema_completion
Create Date: 2026-09-18 17:33:03.678749
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd7246e2552b9'
down_revision: Union[str, Sequence[str], None] = '0003_legacy_schema_completion'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Inventory
    op.execute("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS expired_quantity INTEGER NOT NULL DEFAULT 0")
    
    # Batches
    op.execute("ALTER TABLE batches ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active'")
    op.execute("ALTER TABLE batches ADD COLUMN IF NOT EXISTS expired_at TIMESTAMP")
    
    # Notifications
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(160)")
    op.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_notification_user_dedupe') THEN ALTER TABLE notifications ADD CONSTRAINT uq_notification_user_dedupe UNIQUE (user_id, dedupe_key); END IF; END $$")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_dedupe_key ON notifications (dedupe_key)")
    
    # Inventory Movements
    op.execute("ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS event_key VARCHAR(180)")
    op.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_inventory_movement_event_key') THEN ALTER TABLE inventory_movements ADD CONSTRAINT uq_inventory_movement_event_key UNIQUE (event_key); END IF; END $$")


def downgrade() -> None:
    # Downgrade drops the automation fields if they exist
    op.execute("ALTER TABLE inventory_movements DROP CONSTRAINT IF EXISTS uq_inventory_movement_event_key")
    op.execute("ALTER TABLE inventory_movements DROP COLUMN IF EXISTS event_key")
    op.execute("DROP INDEX IF EXISTS ix_notifications_dedupe_key")
    op.execute("ALTER TABLE notifications DROP CONSTRAINT IF EXISTS uq_notification_user_dedupe")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS dedupe_key")
    op.execute("ALTER TABLE batches DROP COLUMN IF EXISTS expired_at")
    op.execute("ALTER TABLE batches DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE inventory DROP COLUMN IF EXISTS expired_quantity")
