from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.batch import Batch
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


def register_product_serial(db: Session, product: Product, serial: str | None, existing_batch_id: int | None = None) -> str:
    """Register a unique serial for a batch while keeping the legacy product serial."""
    value = normalize_serial(serial)
    existing_batch = None
    if existing_batch_id is not None:
        existing_batch = db.query(Batch).filter(
            Batch.batch_id == existing_batch_id,
            Batch.product_id == product.product_id,
        ).first()
    if existing_batch is not None and existing_batch.serial_number == value:
        if not product.serial_number:
            product.serial_number = value
        return value

    if db.query(Batch.batch_id).filter(Batch.serial_number == value, Batch.product_id != product.product_id).first():
        raise HTTPException(status_code=409, detail=f"Serial number {value} is already registered")
    if db.query(Product.product_id).filter(Product.product_id != product.product_id, Product.serial_number == value).first():
        raise HTTPException(status_code=409, detail=f"Serial number {value} is already registered")
    if not product.serial_number:
        product.serial_number = value
    return value
