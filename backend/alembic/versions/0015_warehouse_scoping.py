"""Scope products, customers, and suppliers to a single warehouse."""

from alembic import op
import sqlalchemy as sa


revision = "0015_warehouse_scoping"
down_revision = "0014_serial_store_orders"
branch_labels = None
depends_on = None

_BACKFILLS = (
    ("products", "product_id", "SELECT MIN(i.warehouse_id) FROM inventory i WHERE i.product_id = products.product_id"),
    ("products", "product_id", "SELECT MIN(r.warehouse_id) FROM inventory_addition_requests r WHERE r.product_id = products.product_id"),
    ("customers", "customer_id", "SELECT MIN(o.warehouse_id) FROM sales_orders o WHERE o.customer_id = customers.customer_id"),
    ("suppliers", "supplier_id", "SELECT MIN(p.warehouse_id) FROM purchase_orders p WHERE p.supplier_id = suppliers.supplier_id"),
)


def upgrade() -> None:
    for table in ("products", "customers", "suppliers"):
        op.add_column(table, sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.warehouse_id"), nullable=True))
        op.create_index(f"ix_{table}_warehouse_id", table, ["warehouse_id"])
    for table, _key, source in _BACKFILLS:
        op.execute(f"UPDATE {table} SET warehouse_id = ({source}) WHERE warehouse_id IS NULL")
    # A single-warehouse install owns every remaining legacy row.
    for table in ("products", "customers", "suppliers"):
        op.execute(f"UPDATE {table} SET warehouse_id = (SELECT MIN(warehouse_id) FROM warehouses) WHERE warehouse_id IS NULL AND (SELECT COUNT(*) FROM warehouses) = 1")
    op.drop_index("ix_products_serial_number", table_name="products")
    op.create_index("ix_products_serial_number", "products", ["serial_number"])
    op.create_unique_constraint("uq_products_warehouse_serial", "products", ["warehouse_id", "serial_number"])


def downgrade() -> None:
    op.drop_constraint("uq_products_warehouse_serial", "products", type_="unique")
    op.drop_index("ix_products_serial_number", table_name="products")
    op.create_index("ix_products_serial_number", "products", ["serial_number"], unique=True)
    for table in ("suppliers", "customers", "products"):
        op.drop_index(f"ix_{table}_warehouse_id", table_name=table)
        op.drop_column(table, "warehouse_id")
