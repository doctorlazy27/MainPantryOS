from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("warehouse_id", "serial_number", name="uq_products_warehouse_serial"),)

    product_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    name: Mapped[str] = mapped_column(String(100))
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.warehouse_id"), nullable=True, index=True)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(100))
    storage_section: Mapped[str] = mapped_column(String(100), nullable=False, default="General")
    shelf_number: Mapped[str] = mapped_column(String(50), nullable=False, default="Unassigned")
    aisle: Mapped[str] = mapped_column(String(50), nullable=False, default="Unassigned")
    quantity: Mapped[int] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(String(50))
    price: Mapped[float] = mapped_column(Float)

    units_per_box: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    reorder_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )