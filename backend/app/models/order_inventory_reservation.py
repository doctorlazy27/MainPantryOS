from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OrderInventoryReservation(Base):
    __tablename__ = "order_inventory_reservations"
    __table_args__ = (
        UniqueConstraint("order_id", "inventory_id", name="uq_order_inventory_reservation_order_inventory"),
        Index("ix_order_inventory_reservations_inventory_status", "inventory_id", "status"),
    )

    reservation_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.order_id"), nullable=False, index=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory.inventory_id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"), nullable=False)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.batch_id"), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.warehouse_id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reserved", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)