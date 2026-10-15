from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Batch(Base):
    __tablename__ = "batches"

    batch_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.product_id"),
        nullable=False
    )

    batch_number: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True
    )

    manufacturing_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    expiry_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    expired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)