from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product


def name_equals(column, value: str):
    """Case-insensitive exact match; ilike would treat % and _ in user input as wildcards."""
    return func.lower(column) == value.strip().lower()


def normalize_serial(serial: str | None) -> str:
    value = (serial or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="A serial number is required")
    if len(value) > 120:
        raise HTTPException(status_code=400, detail="Serial number must be 120 characters or fewer")
    return value


def register_product_serial(db: Session, product: Product, serial: str | None) -> str:
    """Bind one serial to one product line; every batch of that product shares it."""
    value = normalize_serial(serial)
    owner = db.query(Product).filter(
        Product.serial_number == value,
        Product.warehouse_id == product.warehouse_id if product.warehouse_id is not None else Product.warehouse_id.is_(None),
    ).first()
    if owner is not None and owner.product_id != product.product_id:
        raise HTTPException(status_code=409, detail=f"Serial number {value} is already registered to {owner.name}")
    if product.serial_number and product.serial_number != value:
        raise HTTPException(status_code=409, detail=f"{product.name} is already registered with serial number {product.serial_number}")
    product.serial_number = value
    return value
