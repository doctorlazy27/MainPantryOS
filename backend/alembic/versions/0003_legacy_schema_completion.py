"""Move legacy startup schema completion into an explicit migration.

Revision ID: 0003_legacy_schema_completion
Revises: 0002_inventory_recommendations
"""
from alembic import op


revision = "0003_legacy_schema_completion"
down_revision = "0002_inventory_recommendations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS warehouse_id INTEGER REFERENCES warehouses(warehouse_id)")
    op.execute("ALTER TABLE registration_requests ADD COLUMN IF NOT EXISTS warehouse_id INTEGER REFERENCES warehouses(warehouse_id)")
    op.execute("ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS warehouse_id INTEGER REFERENCES warehouses(warehouse_id)")
    op.execute("ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS warehouse_id INTEGER REFERENCES warehouses(warehouse_id)")
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS units_per_box INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS boxed_units INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS units_per_box INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS unit_price DOUBLE PRECISION NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS box_unit_cost DOUBLE PRECISION NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS total_box_cost DOUBLE PRECISION NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE inventory_addition_requests ADD COLUMN IF NOT EXISTS category VARCHAR(100) NOT NULL DEFAULT 'General'")
    op.execute("ALTER TABLE inventory_addition_requests ADD COLUMN IF NOT EXISTS boxed_units INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE inventory_addition_requests ADD COLUMN IF NOT EXISTS units_per_box INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE inventory_addition_requests ADD COLUMN IF NOT EXISTS unit_price DOUBLE PRECISION NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE inventory_addition_requests ADD COLUMN IF NOT EXISTS box_unit_cost DOUBLE PRECISION NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE inventory_addition_requests ADD COLUMN IF NOT EXISTS scanned_code VARCHAR(120)")
    op.execute("CREATE TABLE IF NOT EXISTS boxed_units (boxed_unit_id SERIAL PRIMARY KEY, inventory_id INTEGER NOT NULL REFERENCES inventory(inventory_id), box_code VARCHAR(36) NOT NULL UNIQUE, scanned_code VARCHAR(120), units INTEGER NOT NULL, unit_cost DOUBLE PRECISION NOT NULL DEFAULT 0)")
    op.execute("ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS confirmed_by INTEGER REFERENCES users(user_id)")
    op.execute("ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMP")
    op.execute("CREATE TABLE IF NOT EXISTS warehouse_requests (request_id SERIAL PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(product_id), quantity INTEGER NOT NULL, warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id), requested_by INTEGER NOT NULL REFERENCES users(user_id), approved_by INTEGER REFERENCES users(user_id), status VARCHAR(30) NOT NULL DEFAULT 'pending', created_at TIMESTAMP NOT NULL DEFAULT NOW(), approved_at TIMESTAMP)")
    op.execute("CREATE TABLE IF NOT EXISTS salesperson_inventory (inventory_id SERIAL PRIMARY KEY, salesperson_id INTEGER NOT NULL REFERENCES users(user_id), product_id INTEGER NOT NULL REFERENCES products(product_id), quantity INTEGER NOT NULL DEFAULT 0)")
    op.execute("UPDATE users SET warehouse_id = (SELECT MIN(warehouse_id) FROM warehouses) WHERE warehouse_id IS NULL AND (SELECT COUNT(*) FROM warehouses) = 1")
    op.execute("UPDATE registration_requests SET warehouse_id = (SELECT MIN(warehouse_id) FROM warehouses) WHERE warehouse_id IS NULL AND (SELECT COUNT(*) FROM warehouses) = 1")
    op.execute("UPDATE sales_orders SET warehouse_id = (SELECT warehouse_id FROM users WHERE users.user_id = sales_orders.created_by) WHERE warehouse_id IS NULL")
    op.execute("UPDATE purchase_orders SET warehouse_id = (SELECT warehouse_id FROM users WHERE users.user_id = purchase_orders.created_by) WHERE warehouse_id IS NULL")


def downgrade() -> None:
    # Legacy columns are retained on downgrade to avoid destructive data loss.
    pass