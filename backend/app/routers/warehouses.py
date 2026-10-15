from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.warehouse import Warehouse
from app.schemas.warehouse import WarehouseCreate
from app.auth.dependencies import require_permission


router = APIRouter(
    prefix="/warehouses",
    tags=["Warehouses"]
)


@router.post("/")
def create_warehouse(
    warehouse: WarehouseCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("manage_warehouses"))
):
    new_warehouse = Warehouse(
        name=warehouse.name,
        location=warehouse.location
    )

    db.add(new_warehouse)
    db.commit()
    db.refresh(new_warehouse)

    return new_warehouse


@router.get("/")
def get_warehouses(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_warehouses"))):
    warehouses = db.query(Warehouse).filter(Warehouse.warehouse_id == current_user.get("warehouse_id")).all()

    return {
        "warehouses": warehouses
    }