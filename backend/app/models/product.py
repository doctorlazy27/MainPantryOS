from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    name: Mapped[str] = mapped_column(String(100))
    serial_number: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True, index=True)
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