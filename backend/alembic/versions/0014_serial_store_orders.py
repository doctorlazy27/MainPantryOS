"""Serial numbers, store orders, and manager approval before worker receipt details."""

from alembic import op
import sqlalchemy as sa


revision = "0014_serial_store_orders"
down_revision = "0013_order_reservations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("serial_number", sa.String(length=120), nullable=True))
    op.create_index("ix_products_serial_number", "products", ["serial_number"], unique=True)
    op.add_column("batches", sa.Column("serial_number", sa.String(length=120), nullable=True))
    op.create_index("ix_batches_serial_number", "batches", ["serial_number"])
    op.add_column("inventory_addition_requests", sa.Column("serial_number", sa.String(length=120), nullable=True))
    op.add_column("inventory_addition_requests", sa.Column("received_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True))
    op.add_column("inventory_addition_requests", sa.Column("received_at", sa.DateTime(), nullable=True))
    op.create_table(
        "store_orders",
        sa.Column("store_order_id", sa.Integer(), primary_key=True),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.warehouse_id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.product_id"), nullable=False),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("batches.batch_id"), nullable=False),
        sa.Column("inventory_id", sa.Integer(), sa.ForeignKey("inventory.inventory_id"), nullable=False),
        sa.Column("serial_number", sa.String(length=120), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("needed_by", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("dispatched_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("received_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("dispatched_at", sa.DateTime(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_store_orders_store_order_id", "store_orders", ["store_order_id"])
    op.create_index("ix_store_orders_warehouse_id", "store_orders", ["warehouse_id"])
    op.create_index("ix_store_orders_inventory_id", "store_orders", ["inventory_id"])
    op.create_index("ix_store_orders_status", "store_orders", ["status"])


def downgrade() -> None:
    op.drop_index("ix_store_orders_status", table_name="store_orders")
    op.drop_index("ix_store_orders_inventory_id", table_name="store_orders")
    op.drop_index("ix_store_orders_warehouse_id", table_name="store_orders")
    op.drop_index("ix_store_orders_store_order_id", table_name="store_orders")
    op.drop_table("store_orders")
    op.drop_column("inventory_addition_requests", "received_at")
    op.drop_column("inventory_addition_requests", "received_by")
    op.drop_column("inventory_addition_requests", "serial_number")
    op.drop_index("ix_batches_serial_number", table_name="batches")
    op.drop_column("batches", "serial_number")
    op.drop_index("ix_products_serial_number", table_name="products")
    op.drop_column("products", "serial_number")
