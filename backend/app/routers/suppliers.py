from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.supplier import Supplier
from app.schemas.supplier import SupplierCreate
from app.auth.dependencies import require_permission


router = APIRouter(
    prefix="/suppliers",
    tags=["Suppliers"]
)


@router.post("/")
def create_supplier(
    supplier: SupplierCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("create_purchase_orders"))
):
    new_supplier = Supplier(
        name=supplier.name,
        phone=supplier.phone,
        email=supplier.email,
        address=supplier.address,
        warehouse_id=current_user.get("warehouse_id"),
    )

    db.add(new_supplier)
    db.commit()
    db.refresh(new_supplier)

    return new_supplier


@router.get("/")
def get_suppliers(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_suppliers"))):
    suppliers = db.query(Supplier).filter(Supplier.warehouse_id == current_user.get("warehouse_id")).all()

    return {
        "suppliers": suppliers
    }