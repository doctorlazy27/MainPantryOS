from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date
from fastapi import HTTPException

from app.database import get_db
from app.models.batch import Batch
from app.schemas.batch import BatchCreate
from app.models.product import Product
from app.services.serial import register_product_serial
from app.auth.dependencies import require_permission


router = APIRouter(
    prefix="/batches",
    tags=["Batches"]
)


@router.post("/")
def create_batch(
    batch: BatchCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("receive_purchase_orders"))
):
    if batch.expiry_date <= batch.manufacturing_date:
        raise HTTPException(status_code=400, detail="Expiry date must be after manufacturing date")
    if batch.expiry_date <= date.today():
        raise HTTPException(status_code=400, detail="Cannot create an already expired batch")
    product = db.query(Product).filter(Product.product_id == batch.product_id, Product.warehouse_id == current_user.get("warehouse_id")).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    serial = register_product_serial(db, product, batch.serial_number)
    new_batch = Batch(
        product_id=batch.product_id,
        serial_number=serial,
        batch_number=batch.batch_number,
        manufacturing_date=batch.manufacturing_date,
        expiry_date=batch.expiry_date
    )

    db.add(new_batch)
    db.commit()
    db.refresh(new_batch)

    return new_batch


@router.get("/")
def get_batches(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_inventory"))):
    batches = db.query(Batch).join(Product, Batch.product_id == Product.product_id).filter(
        Product.warehouse_id == current_user.get("warehouse_id")
    ).all()

    return {
        "batches": batches
    }