from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OrderPickScan(Base):
    __tablename__ = "order_pick_scans"

    pick_scan_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_key: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.order_id"), nullable=False, index=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory.inventory_id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"), nullable=False)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.batch_id"), nullable=False)
    boxed_unit_id: Mapped[int | None] = mapped_column(ForeignKey("boxed_units.boxed_unit_id"), nullable=True)
    scanned_code: Mapped[str] = mapped_column(String(120), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)