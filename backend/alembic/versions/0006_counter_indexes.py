"""Align counter indexes with ORM metadata.

Revision ID: 0006_counter_indexes
Revises: 0005_counter_checkout
"""
from alembic import op


revision = "0006_counter_indexes"
down_revision = "0005_counter_checkout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_counter_inventory_warehouse")
    for name, table, column in [
        ("ix_counter_inventory_counter_inventory_id", "counter_inventory", "counter_inventory_id"),
        ("ix_counter_inventory_warehouse_id", "counter_inventory", "warehouse_id"),
        ("ix_counter_inventory_product_id", "counter_inventory", "product_id"),
        ("ix_counter_inventory_batch_id", "counter_inventory", "batch_id"),
        ("ix_counter_allocations_allocation_id", "counter_allocations", "allocation_id"),
        ("ix_counter_allocations_warehouse_id", "counter_allocations", "warehouse_id"),
        ("ix_counter_sales_sale_id", "counter_sales", "sale_id"),
        ("ix_counter_sales_warehouse_id", "counter_sales", "warehouse_id"),
        ("ix_counter_sale_items_sale_item_id", "counter_sale_items", "sale_item_id"),
        ("ix_counter_sale_items_sale_id", "counter_sale_items", "sale_id"),
    ]:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})")


def downgrade() -> None:
    for name in [
        "ix_counter_inventory_counter_inventory_id", "ix_counter_inventory_warehouse_id", "ix_counter_inventory_product_id", "ix_counter_inventory_batch_id",
        "ix_counter_allocations_allocation_id", "ix_counter_allocations_warehouse_id", "ix_counter_sales_sale_id", "ix_counter_sales_warehouse_id",
        "ix_counter_sale_items_sale_item_id", "ix_counter_sale_items_sale_id",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {name}")