from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, aliased

from app.auth.dependencies import require_permission
from app.database import get_db
from app.models.inventory import Inventory
from app.models.inventory_movement import InventoryMovement
from app.models.warehouse import Warehouse
from app.models.stock_transfer import StockTransfer
from app.models.product import Product
from app.models.batch import Batch
from app.schemas.stock_transfer import StockTransferCreate
from app.auth.dependencies import require_permission
from app.models.inventory import Inventory
from app.services.activity import log_activity
from app.services.inventory_guard import require_available_batch
from app.services.order_reservations import available_quantity


router = APIRouter(
    prefix="/stock-transfers",
    tags=["Stock Transfers"]
)


@router.get("/")
def list_stock_transfers(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_stock_transfers")),
):
    source_warehouse = aliased(Warehouse)
    destination_warehouse = aliased(Warehouse)
    query = db.query(
        StockTransfer,
        Product.name,
        Batch.batch_number,
        source_warehouse.name,
        destination_warehouse.name,
    ).join(
        Product, StockTransfer.product_id == Product.product_id
    ).join(
        Batch, StockTransfer.batch_id == Batch.batch_id
    ).join(
        source_warehouse, StockTransfer.source_warehouse_id == source_warehouse.warehouse_id
    ).join(
        destination_warehouse, StockTransfer.destination_warehouse_id == destination_warehouse.warehouse_id
    )
    if current_user["role"] == "manager":
        warehouse_id = current_user.get("warehouse_id")
        query = query.filter(or_(
            StockTransfer.source_warehouse_id == warehouse_id,
            StockTransfer.destination_warehouse_id == warehouse_id,
        ))
    else:
        query = query.filter(
            StockTransfer.created_by == current_user["user_id"],
            StockTransfer.source_warehouse_id == current_user.get("warehouse_id"),
        )
    rows = query.order_by(StockTransfer.created_at.desc()).limit(100).all()
    return {"transfers": [{
        "transfer_id": transfer.transfer_id,
        "product_id": transfer.product_id,
        "product_name": product_name,
        "batch_id": transfer.batch_id,
        "batch_number": batch_number,
        "source_warehouse_id": transfer.source_warehouse_id,
        "source_warehouse_name": source_name,
        "destination_warehouse_id": transfer.destination_warehouse_id,
        "destination_warehouse_name": destination_name,
        "quantity": transfer.quantity,
        "status": transfer.status,
        "created_at": transfer.created_at,
    } for transfer, product_name, batch_number, source_name, destination_name in rows]}


@router.patch("/{transfer_id}/approve")
def approve_stock_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("approve_stock_transfers")
    )
):
    transfer = db.query(StockTransfer).filter(
        StockTransfer.transfer_id == transfer_id
    ).with_for_update().first()

    if transfer is None:
        raise HTTPException(
            status_code=404,
            detail="Stock transfer not found"
        )

    if current_user["role"] == "manager" and current_user.get("warehouse_id") not in {
        transfer.source_warehouse_id,
        transfer.destination_warehouse_id,
    }:
        raise HTTPException(status_code=403, detail="This transfer does not involve your warehouse")

    if transfer.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Only pending transfers can be approved"
        )

    require_available_batch(db, transfer.batch_id)

    source_inventory = db.query(Inventory).filter(
        Inventory.product_id == transfer.product_id,
        Inventory.batch_id == transfer.batch_id,
        Inventory.warehouse_id == transfer.source_warehouse_id
    ).with_for_update().first()

    if source_inventory is None:
        raise HTTPException(
            status_code=404,
            detail="Source inventory not found"
        )

    if source_inventory.putaway_status != "confirmed":
        raise HTTPException(status_code=409, detail="Source stock must be put away before transfer")

    if available_quantity(db, source_inventory) < transfer.quantity:
        raise HTTPException(
            status_code=400,
            detail="Insufficient stock for transfer"
        )

    destination_inventory = db.query(Inventory).filter(
        Inventory.product_id == transfer.product_id,
        Inventory.batch_id == transfer.batch_id,
        Inventory.warehouse_id == transfer.destination_warehouse_id
    ).with_for_update().first()

    source_inventory.quantity -= transfer.quantity
    db.add(InventoryMovement(
        inventory_id=source_inventory.inventory_id,
        product_id=source_inventory.product_id,
        batch_id=source_inventory.batch_id,
        warehouse_id=source_inventory.warehouse_id,
        movement_type="TRANSFERRED",
        quantity=transfer.quantity,
        actor_id=current_user["user_id"],
        actor_name=current_user["username"],
        reason=f"Stock transfer #{transfer.transfer_id} to warehouse {transfer.destination_warehouse_id}.",
    ))

    if destination_inventory:
        destination_inventory.quantity += transfer.quantity
    else:
        destination_inventory = Inventory(
            product_id=transfer.product_id,
            warehouse_id=transfer.destination_warehouse_id,
            batch_id=transfer.batch_id,
            quantity=transfer.quantity,
            storage_zone=source_inventory.storage_zone,
            location_code="STAGING",
            putaway_status="pending",
        )

        db.add(destination_inventory)
        db.flush()

    db.add(InventoryMovement(
        inventory_id=destination_inventory.inventory_id,
        product_id=destination_inventory.product_id,
        batch_id=destination_inventory.batch_id,
        warehouse_id=destination_inventory.warehouse_id,
        movement_type="RECEIVED",
        quantity=transfer.quantity,
        actor_id=current_user["user_id"],
        actor_name=current_user["username"],
        reason=f"Stock transfer #{transfer.transfer_id} from warehouse {transfer.source_warehouse_id}.",
    ))

    transfer.status = "completed"
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="complete_stock_transfer",
    description=f"Completed stock transfer #{transfer.transfer_id}"
)
    

    db.commit()
    db.refresh(transfer)

    return {
        "message": "Stock transfer completed successfully",
        "transfer_id": transfer.transfer_id,
        "status": transfer.status,
        "approved_by": current_user["username"]
    }

@router.post("/")
def create_stock_transfer(
    transfer: StockTransferCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("request_stock_transfer")
    )
):
    if transfer.source_warehouse_id == transfer.destination_warehouse_id:
        raise HTTPException(
            status_code=400,
            detail="Source and destination warehouses must be different"
        )

    if transfer.source_warehouse_id != current_user.get("warehouse_id"):
        raise HTTPException(status_code=403, detail="You can only initiate transfers from your assigned warehouse")

    if db.query(Warehouse).filter(Warehouse.warehouse_id.in_([
        transfer.source_warehouse_id,
        transfer.destination_warehouse_id,
    ])).count() != 2:
        raise HTTPException(status_code=404, detail="Source or destination warehouse not found")

    inventory = db.query(Inventory).filter(
        Inventory.product_id == transfer.product_id,
        Inventory.batch_id == transfer.batch_id,
        Inventory.warehouse_id == transfer.source_warehouse_id
    ).first()

    if inventory is None:
        raise HTTPException(
            status_code=404,
            detail="Source inventory not found"
        )

    require_available_batch(db, transfer.batch_id)

    if inventory.quantity < transfer.quantity:
        raise HTTPException(
            status_code=400,
            detail="Insufficient stock for transfer"
        )

    new_transfer = StockTransfer(
        product_id=transfer.product_id,
        batch_id=transfer.batch_id,
        source_warehouse_id=transfer.source_warehouse_id,
        destination_warehouse_id=transfer.destination_warehouse_id,
        quantity=transfer.quantity,
        created_by=current_user["user_id"],
        status="pending"
    )

    db.add(new_transfer)
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="request_stock_transfer",
    description=f"Requested stock transfer #{new_transfer.transfer_id}"
)
    db.commit()
    db.refresh(new_transfer)

    return {
        "message": "Stock transfer request created",
        "transfer_id": new_transfer.transfer_id,
        "status": new_transfer.status,
        "created_by": current_user["username"]
    }



@router.patch("/{transfer_id}/reject")
def reject_stock_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("approve_stock_transfers")
    )
):
    transfer = db.query(StockTransfer).filter(
        StockTransfer.transfer_id == transfer_id
    ).with_for_update().first()

    if transfer is None:
        raise HTTPException(
            status_code=404,
            detail="Stock transfer not found"
        )

    if current_user["role"] == "manager" and current_user.get("warehouse_id") not in {
        transfer.source_warehouse_id,
        transfer.destination_warehouse_id,
    }:
        raise HTTPException(status_code=403, detail="This transfer does not involve your warehouse")

    if transfer.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Only pending transfers can be rejected"
        )

    transfer.status = "rejected"
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="reject_stock_transfer",
    description=f"Rejected stock transfer #{transfer.transfer_id}"
)
    
    db.commit()
    db.refresh(transfer)

    return {
        "message": "Stock transfer rejected",
        "transfer_id": transfer.transfer_id,
        "status": transfer.status,
        "rejected_by": current_user["username"]
    }