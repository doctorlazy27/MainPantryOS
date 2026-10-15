"""Harden expiry automation and notification idempotency.

Revision ID: 0001_automation_hardening
Revises: 0000_initial_schema
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_automation_hardening"
down_revision = "0000_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS expired_quantity INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE batches ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active'")
    op.execute("ALTER TABLE batches ADD COLUMN IF NOT EXISTS expired_at TIMESTAMP")
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(160)")
    op.execute("CREATE TABLE IF NOT EXISTS inventory_movements (movement_id SERIAL PRIMARY KEY, inventory_id INTEGER NOT NULL REFERENCES inventory(inventory_id), product_id INTEGER NOT NULL REFERENCES products(product_id), batch_id INTEGER NOT NULL REFERENCES batches(batch_id), warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id), movement_type VARCHAR(30) NOT NULL, quantity INTEGER NOT NULL, actor_id INTEGER REFERENCES users(user_id), actor_name VARCHAR(100) NOT NULL DEFAULT 'SYSTEM', reason TEXT NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT NOW())")
    op.execute("ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS event_key VARCHAR(180)")
    op.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_notification_user_dedupe') THEN ALTER TABLE notifications ADD CONSTRAINT uq_notification_user_dedupe UNIQUE (user_id, dedupe_key); END IF; END $$")
    op.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_inventory_movement_event_key') THEN ALTER TABLE inventory_movements ADD CONSTRAINT uq_inventory_movement_event_key UNIQUE (event_key); END IF; END $$")


def downgrade() -> None:
    op.execute("ALTER TABLE inventory_movements DROP CONSTRAINT IF EXISTS uq_inventory_movement_event_key")
    op.execute("ALTER TABLE notifications DROP CONSTRAINT IF EXISTS uq_notification_user_dedupe")
    op.execute("ALTER TABLE inventory_movements DROP COLUMN IF EXISTS event_key")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS dedupe_key")
    op.execute("ALTER TABLE batches DROP COLUMN IF EXISTS expired_at")
    op.execute("ALTER TABLE batches DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE inventory DROP COLUMN IF EXISTS expired_quantity")
