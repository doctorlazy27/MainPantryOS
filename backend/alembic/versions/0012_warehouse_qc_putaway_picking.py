"""Add receiving QC, putaway, and order-pick workflow state.

Revision ID: 0012_warehouse_workflow
Revises: 0011_salesperson_to_manager, d7246e2552b9
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_warehouse_workflow"
down_revision = ("0011_salesperson_to_manager", "d7246e2552b9")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory", sa.Column("storage_zone", sa.String(length=30), nullable=False, server_default="AMBIENT"))
    op.add_column("inventory", sa.Column("location_code", sa.String(length=100), nullable=False, server_default="UNASSIGNED"))
    op.add_column("inventory", sa.Column("putaway_status", sa.String(length=20), nullable=False, server_default="confirmed"))
    op.create_table(
        "temperature_logs",
        sa.Column("temperature_log_id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("batches.batch_id"), nullable=False),
        sa.Column("inventory_id", sa.Integer(), sa.ForeignKey("inventory.inventory_id"), nullable=True),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.warehouse_id"), nullable=False),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("stage", sa.String(length=30), nullable=False),
        sa.Column("storage_zone", sa.String(length=30), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=False),
        sa.Column("minimum_c", sa.Float(), nullable=False),
        sa.Column("maximum_c", sa.Float(), nullable=True),
        sa.Column("within_range", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_temperature_logs_temperature_log_id", "temperature_logs", ["temperature_log_id"])
    op.create_index("ix_temperature_logs_batch_id", "temperature_logs", ["batch_id"])
    op.create_index("ix_temperature_logs_warehouse_id", "temperature_logs", ["warehouse_id"])
    op.create_table(
        "order_pick_scans",
        sa.Column("pick_scan_id", sa.Integer(), primary_key=True),
        sa.Column("event_key", sa.String(length=180), nullable=False, unique=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("sales_orders.order_id"), nullable=False),
        sa.Column("inventory_id", sa.Integer(), sa.ForeignKey("inventory.inventory_id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.product_id"), nullable=False),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("batches.batch_id"), nullable=False),
        sa.Column("boxed_unit_id", sa.Integer(), sa.ForeignKey("boxed_units.boxed_unit_id"), nullable=True),
        sa.Column("scanned_code", sa.String(length=120), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_order_pick_scans_pick_scan_id", "order_pick_scans", ["pick_scan_id"])
    op.create_index("ix_order_pick_scans_order_id", "order_pick_scans", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_pick_scans_order_id", table_name="order_pick_scans")
    op.drop_index("ix_order_pick_scans_pick_scan_id", table_name="order_pick_scans")
    op.drop_table("order_pick_scans")
    op.drop_index("ix_temperature_logs_warehouse_id", table_name="temperature_logs")
    op.drop_index("ix_temperature_logs_batch_id", table_name="temperature_logs")
    op.drop_index("ix_temperature_logs_temperature_log_id", table_name="temperature_logs")
    op.drop_table("temperature_logs")
    op.drop_column("inventory", "putaway_status")
    op.drop_column("inventory", "location_code")
    op.drop_column("inventory", "storage_zone")