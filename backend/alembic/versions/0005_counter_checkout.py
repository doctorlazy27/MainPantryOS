"""Add counter inventory, allocations, and checkout bills.

Revision ID: 0005_counter_checkout
Revises: 0004_barcode_consumption
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0005_counter_checkout"
down_revision: Union[str, Sequence[str], None] = "0004_barcode_consumption"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS counter_inventory (
        counter_inventory_id SERIAL PRIMARY KEY,
        warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
        product_id INTEGER NOT NULL REFERENCES products(product_id),
        batch_id INTEGER NOT NULL REFERENCES batches(batch_id),
        quantity INTEGER NOT NULL DEFAULT 0,
        minimum_level INTEGER NOT NULL DEFAULT 0,
        unit_price DOUBLE PRECISION NOT NULL DEFAULT 0,
        last_replenished_at TIMESTAMP,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )""")
    op.execute("DROP INDEX IF EXISTS ix_counter_inventory_warehouse")
    op.execute("CREATE INDEX IF NOT EXISTS ix_counter_inventory_counter_inventory_id ON counter_inventory(counter_inventory_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_counter_inventory_warehouse_id ON counter_inventory(warehouse_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_counter_inventory_product_id ON counter_inventory(product_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_counter_inventory_batch_id ON counter_inventory(batch_id)")
    op.execute("""CREATE TABLE IF NOT EXISTS counter_allocations (
        allocation_id SERIAL PRIMARY KEY,
        warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
        product_id INTEGER NOT NULL REFERENCES products(product_id),
        quantity INTEGER NOT NULL,
        status VARCHAR(30) NOT NULL DEFAULT 'pending',
        requested_by INTEGER NOT NULL REFERENCES users(user_id),
        reviewed_by INTEGER REFERENCES users(user_id),
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        reviewed_at TIMESTAMP
    )""")
    op.execute("""CREATE TABLE IF NOT EXISTS counter_sales (
        sale_id SERIAL PRIMARY KEY,
        warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
        bill_number VARCHAR(40) NOT NULL UNIQUE,
        total_amount DOUBLE PRECISION NOT NULL,
        worker_id INTEGER NOT NULL REFERENCES users(user_id),
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )""")
    op.execute("""CREATE TABLE IF NOT EXISTS counter_sale_items (
        sale_item_id SERIAL PRIMARY KEY,
        sale_id INTEGER NOT NULL REFERENCES counter_sales(sale_id),
        product_id INTEGER NOT NULL REFERENCES products(product_id),
        batch_id INTEGER NOT NULL REFERENCES batches(batch_id),
        quantity INTEGER NOT NULL,
        unit_price DOUBLE PRECISION NOT NULL,
        line_total DOUBLE PRECISION NOT NULL
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_counter_allocations_allocation_id ON counter_allocations(allocation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_counter_allocations_warehouse_id ON counter_allocations(warehouse_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_counter_sales_sale_id ON counter_sales(sale_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_counter_sales_warehouse_id ON counter_sales(warehouse_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_counter_sale_items_sale_item_id ON counter_sale_items(sale_item_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_counter_sale_items_sale_id ON counter_sale_items(sale_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS counter_sale_items")
    op.execute("DROP TABLE IF EXISTS counter_sales")
    op.execute("DROP TABLE IF EXISTS counter_allocations")
    op.execute("DROP TABLE IF EXISTS counter_inventory")