from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CounterSale(Base):
    __tablename__ = "counter_sales"
    __table_args__ = (UniqueConstraint("worker_id", "request_key", name="uq_counter_sale_worker_request_key"),)

    sale_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.warehouse_id"), nullable=False, index=True)
    bill_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    worker_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    request_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class CounterSaleItem(Base):
    __tablename__ = "counter_sale_items"

    sale_item_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("counter_sales.sale_id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"), nullable=False)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.batch_id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    line_total: Mapped[float] = mapped_column(Float, nullable=False)