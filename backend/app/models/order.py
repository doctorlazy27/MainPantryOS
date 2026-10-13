from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SalesOrder(Base):
    __tablename__ = "sales_orders"

    order_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.customer_id"),
        nullable=False
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=False
    )

    warehouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouses.warehouse_id"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reservation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="none")