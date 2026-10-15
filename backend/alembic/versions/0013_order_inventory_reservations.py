"""Reserve inventory for approved sales orders."""

from datetime import date

from alembic import op
import sqlalchemy as sa


revision = "0013_order_reservations"
down_revision = "0012_warehouse_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order_pick_scans", sa.Column("actor_name", sa.String(length=150), nullable=True))
    op.execute("UPDATE order_pick_scans SET actor_name = (SELECT full_name FROM users WHERE users.user_id = order_pick_scans.actor_id) WHERE actor_name IS NULL")
    op.add_column("counter_sales", sa.Column("request_key", sa.String(length=100), nullable=True))
    op.create_index("uq_counter_sale_worker_request_key", "counter_sales", ["worker_id", "request_key"], unique=True)
    op.add_column(
        "sales_orders",
        sa.Column("reservation_status", sa.String(length=20), nullable=False, server_default="none"),
    )
    op.create_table(
        "order_inventory_reservations",
        sa.Column("reservation_id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("sales_orders.order_id"), nullable=False),
        sa.Column("inventory_id", sa.Integer(), sa.ForeignKey("inventory.inventory_id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.product_id"), nullable=False),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("batches.batch_id"), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.warehouse_id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="reserved"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("order_id", "inventory_id", name="uq_order_inventory_reservation_order_inventory"),
    )
    op.create_index("ix_order_inventory_reservations_reservation_id", "order_inventory_reservations", ["reservation_id"])
    op.create_index("ix_order_inventory_reservations_order_id", "order_inventory_reservations", ["order_id"])
    op.create_index("ix_order_inventory_reservations_warehouse_id", "order_inventory_reservations", ["warehouse_id"])
    op.create_index("ix_order_inventory_reservations_status", "order_inventory_reservations", ["status"])
    op.create_index("ix_order_inventory_reservations_inventory_status", "order_inventory_reservations", ["inventory_id", "status"])

    bind = op.get_bind()
    metadata = sa.MetaData()
    orders = sa.Table("sales_orders", metadata, autoload_with=bind)
    order_items = sa.Table("sales_order_items", metadata, autoload_with=bind)
    inventory = sa.Table("inventory", metadata, autoload_with=bind)
    batches = sa.Table("batches", metadata, autoload_with=bind)
    reservations = sa.Table("order_inventory_reservations", metadata, autoload_with=bind)
    approved_orders = bind.execute(
        sa.select(orders.c.order_id, orders.c.warehouse_id)
        .where(orders.c.status == "approved", orders.c.warehouse_id.is_not(None))
        .order_by(orders.c.created_at, orders.c.order_id)
    ).all()

    for order_id, warehouse_id in approved_orders:
        order_complete = True
        lines = bind.execute(
            sa.select(order_items.c.product_id, sa.func.sum(order_items.c.quantity).label("quantity"))
            .where(order_items.c.order_id == order_id)
            .group_by(order_items.c.product_id)
        ).all()
        for product_id, requested_quantity in lines:
            remaining = int(requested_quantity)
            candidates = bind.execute(
                sa.select(
                    inventory.c.inventory_id,
                    inventory.c.batch_id,
                    inventory.c.quantity,
                )
                .select_from(inventory.join(batches, inventory.c.batch_id == batches.c.batch_id))
                .where(
                    inventory.c.product_id == product_id,
                    inventory.c.warehouse_id == warehouse_id,
                    inventory.c.quantity > 0,
                    inventory.c.putaway_status == "confirmed",
                    batches.c.status == "active",
                    batches.c.expiry_date >= date.today(),
                )
                .order_by(batches.c.expiry_date, inventory.c.inventory_id)
            ).all()
            for inventory_id, batch_id, stock_quantity in candidates:
                already_reserved = bind.execute(
                    sa.select(sa.func.coalesce(sa.func.sum(reservations.c.quantity), 0)).where(
                        reservations.c.inventory_id == inventory_id,
                        reservations.c.status == "reserved",
                    )
                ).scalar_one()
                available = max(int(stock_quantity) - int(already_reserved or 0), 0)
                allocated = min(available, remaining)
                if allocated:
                    bind.execute(reservations.insert().values(
                        order_id=order_id,
                        inventory_id=inventory_id,
                        product_id=product_id,
                        batch_id=batch_id,
                        warehouse_id=warehouse_id,
                        quantity=allocated,
                        status="reserved",
                    ))
                    remaining -= allocated
                if remaining == 0:
                    break
            if remaining:
                order_complete = False
        bind.execute(
            orders.update().where(orders.c.order_id == order_id).values(
                reservation_status="reserved" if order_complete else "short"
            )
        )


def downgrade() -> None:
    op.drop_index("uq_counter_sale_worker_request_key", table_name="counter_sales")
    op.drop_column("counter_sales", "request_key")
    op.drop_index("ix_order_inventory_reservations_inventory_status", table_name="order_inventory_reservations")
    op.drop_index("ix_order_inventory_reservations_status", table_name="order_inventory_reservations")
    op.drop_index("ix_order_inventory_reservations_warehouse_id", table_name="order_inventory_reservations")
    op.drop_index("ix_order_inventory_reservations_order_id", table_name="order_inventory_reservations")
    op.drop_index("ix_order_inventory_reservations_reservation_id", table_name="order_inventory_reservations")
    op.drop_table("order_inventory_reservations")
    op.drop_column("sales_orders", "reservation_status")
    op.drop_column("order_pick_scans", "actor_name")