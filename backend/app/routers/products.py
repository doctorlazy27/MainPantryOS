from fastapi import APIRouter, Depends, HTTPException
from datetime import date
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.product import Product
from app.schemas.product import ProductCreate
from app.models.inventory import Inventory
from app.models.batch import Batch
from app.auth.dependencies import get_current_user, require_permission

router = APIRouter(
    prefix="/products",
    tags=["Products"]
)

@router.get("/")
def get_products(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_inventory"))):
    products = db.query(Product).all()

    return {
        "products": products
    }

@router.get("/low-stock")
def get_low_stock_products(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_inventory"))):
    products = db.query(Product).all()
    low_stock = []

    for product in products:
        total_quantity = sum(
            quantity for (quantity,) in db.query(Inventory.quantity).filter(
                    Inventory.product_id == product.product_id,
                    Inventory.warehouse_id == current_user.get("warehouse_id"),
            ).all()
        )
        if total_quantity <= product.reorder_level:
            low_stock.append({
                "product_id": product.product_id,
                "name": product.name,
                "reorder_level": product.reorder_level,
                "current_quantity": total_quantity,
                "unit": product.unit,
            })

    return {"low_stock": low_stock}


@router.get("/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_inventory"))):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if product is None:
        return {"message": "Product not found"}
    return product


