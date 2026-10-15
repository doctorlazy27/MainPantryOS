from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False
    )

    phone: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    email: Mapped[str] = mapped_column(
        String(150),
        nullable=True
    )

    address: Mapped[str] = mapped_column(
        String(250),
        nullable=True
    )

    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.warehouse_id"), nullable=True, index=True)