from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.database import get_db
from app.models.batch import Batch
from app.models.counter_inventory import CounterInventory
from app.models.inventory import Inventory
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.store_order import StoreOrder
from app.schemas.store_order import StoreOrderCreate, StoreOrderReject
from app.services.activity import log_activity
from app.services.notification import create_notification, notify_roles
from app.services.order_reservations import available_quantity

router = APIRouter(prefix="/store-orders", tags=["Store Orders"])


def _pending_quantity(db: Session, inventory_id: int) -> int:
    return int(db.query(func.coalesce(func.sum(StoreOrder.quantity), 0)).filter(
        StoreOrder.inventory_id == inventory_id,
        StoreOrder.status == "pending",
    ).scalar() or 0)


def _order_payload(order: StoreOrder, product_name: str, batch_number: str) -> dict:
    return {
        "store_order_id": order.store_order_id,
        "product_id": order.product_id,
        "product_name": product_name,
        "batch_id": order.batch_id,
        "batch_number": batch_number,
        "serial_number": order.serial_number,
        "quantity": order.quantity,
        "needed_by": order.needed_by,
        "status": order.status,
        "note": order.note,
        "created_at": order.created_at,
        "dispatched_at": order.dispatched_at,
        "received_at": order.received_at,
    }


@router.get("/available")
def list_available_batches(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_store_orders")),
):
    warehouse_id = current_user.get("warehouse_id")
    rows = db.query(Inventory, Product, Batch).join(
        Product, Inventory.product_id == Product.product_id
    ).join(Batch, Inventory.batch_id == Batch.batch_id).filter(
        Inventory.warehouse_id == warehouse_id,
        Inventory.quantity > 0,
        Inventory.putaway_status == "confirmed",
        Batch.status == "active",
        Batch.expiry_date > date.today(),
    ).order_by(Product.name.asc(), Batch.expiry_date.asc()).all()
    counter_totals = {
        product_id: (int(quantity or 0), int(minimum or 0))
        for product_id, quantity, minimum in db.query(
            CounterInventory.product_id,
            func.sum(CounterInventory.quantity),
            func.max(CounterInventory.minimum_level),
        ).filter(CounterInventory.warehouse_id == warehouse_id).group_by(CounterInventory.product_id).all()
    }
    items = []
    for inventory, product, batch in rows:
        available = available_quantity(db, inventory) - _pending_quantity(db, inventory.inventory_id)
        if available <= 0:
            continue
        counter_quantity, minimum_level = counter_totals.get(product.product_id, (0, product.reorder_level))
        items.append({
            "inventory_id": inventory.inventory_id,
            "product_id": product.product_id,
            "product_name": product.name,
            "serial_number": batch.serial_number or product.serial_number,
            "batch_id": batch.batch_id,
            "batch_number": batch.batch_number,
            "expiry_date": batch.expiry_date,
            "available_quantity": available,
            "counter_quantity": counter_quantity,
            "counter_minimum": minimum_level,
            "counter_low": counter_quantity < minimum_level,
        })
    return {"items": items}


@router.get("/")
def list_store_orders(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_store_orders")),
):
    rows = db.query(StoreOrder, Product.name, Batch.batch_number).join(
        Product, StoreOrder.product_id == Product.product_id
    ).join(Batch, StoreOrder.batch_id == Batch.batch_id).filter(
        StoreOrder.warehouse_id == current_user.get("warehouse_id")
    ).order_by(StoreOrder.created_at.desc()).limit(200).all()
    return {"orders": [_order_payload(order, name, batch_number) for order, name, batch_number in rows]}


@router.post("/")
def create_store_order(
    request: StoreOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("request_store_orders")),
):
    warehouse_id = current_user.get("warehouse_id")
    inventory = db.query(Inventory).filter(
        Inventory.inventory_id == request.inventory_id,
        Inventory.warehouse_id == warehouse_id,
    ).with_for_update().first()
    if inventory is None:
        raise HTTPException(status_code=404, detail="Inventory batch not found in your warehouse")
    batch = db.query(Batch).filter(Batch.batch_id == inventory.batch_id).first()
    product = db.query(Product).filter(Product.product_id == inventory.product_id).first()
    if batch is None or product is None or batch.status != "active" or batch.expiry_date <= date.today() or inventory.putaway_status != "confirmed":
        raise HTTPException(status_code=400, detail="Only active, unexpired, shelved batches can be ordered")
    serial = batch.serial_number or product.serial_number
    if not serial:
        raise HTTPException(status_code=409, detail="This batch has no registered serial number")
    available = available_quantity(db, inventory) - _pending_quantity(db, inventory.inventory_id)
    if request.quantity > available:
        raise HTTPException(status_code=400, detail=f"Only {max(available, 0)} units of this batch are available")
    needed_by = request.needed_by.replace(tzinfo=None) if request.needed_by.tzinfo else request.needed_by
    order = StoreOrder(
        warehouse_id=warehouse_id,
        product_id=product.product_id,
        batch_id=batch.batch_id,
        inventory_id=inventory.inventory_id,
        serial_number=serial,
        quantity=request.quantity,
        needed_by=needed_by,
        requested_by=current_user["user_id"],
    )
    db.add(order)
    db.flush()
    notify_roles(db, {"warehouse_worker"}, "Store batch order", f"Store order #{order.store_order_id}: {request.quantity} x {product.name} (serial {serial}) is needed by {needed_by:%Y-%m-%d %H:%M}.", "store_order_requested", warehouse_id)
    log_activity(db, current_user["user_id"], current_user["username"], "STORE_ORDER_REQUESTED", f"Requested {request.quantity} x {product.name} serial {serial} for the store.")
    db.commit()
    return {"store_order_id": order.store_order_id, "status": order.status, "serial_number": serial}


def _load_order(db: Session, store_order_id: int, current_user: dict, status: str) -> StoreOrder:
    order = db.query(StoreOrder).filter(
        StoreOrder.store_order_id == store_order_id,
        StoreOrder.warehouse_id == current_user.get("warehouse_id"),
        StoreOrder.status == status,
    ).with_for_update().first()
    if order is None:
        raise HTTPException(status_code=404, detail=f"No {status} store order found")
    return order


@router.patch("/{store_order_id}/dispatch")
def dispatch_store_order(
    store_order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("dispatch_store_orders")),
):
    order = _load_order(db, store_order_id, current_user, "pending")
    inventory = db.query(Inventory).filter(Inventory.inventory_id == order.inventory_id).with_for_update().first()
    batch = db.query(Batch).filter(Batch.batch_id == order.batch_id).with_for_update().first()
    if inventory is None or batch is None or batch.status != "active" or batch.expiry_date <= date.today() or inventory.putaway_status != "confirmed":
        raise HTTPException(status_code=409, detail="This batch is no longer available; reject the order")
    if available_quantity(db, inventory) < order.quantity:
        raise HTTPException(status_code=409, detail="Not enough unreserved stock remains in this batch; reject the order")
    inventory.quantity -= order.quantity
    order.status = "dispatched"
    order.dispatched_by = current_user["user_id"]
    order.dispatched_at = datetime.utcnow()
    db.add(InventoryMovement(
        inventory_id=inventory.inventory_id,
        product_id=order.product_id,
        batch_id=order.batch_id,
        warehouse_id=order.warehouse_id,
        movement_type="DISPATCHED_TO_STORE",
        event_key=f"store_order_dispatch:{order.store_order_id}",
        quantity=order.quantity,
        actor_id=current_user["user_id"],
        actor_name=current_user["username"],
        reason=f"Store order #{order.store_order_id} dispatched (serial {order.serial_number}).",
    ))
    create_notification(db, order.requested_by, "Store order dispatched", f"Store order #{order.store_order_id} was dispatched. Confirm it when the store receives it.", "store_order_dispatched")
    log_activity(db, current_user["user_id"], current_user["username"], "STORE_ORDER_DISPATCHED", f"Dispatched store order #{order.store_order_id}.")
    db.commit()
    return {"store_order_id": order.store_order_id, "status": order.status}


@router.patch("/{store_order_id}/reject")
def reject_store_order(
    store_order_id: int,
    body: StoreOrderReject | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("dispatch_store_orders")),
):
    order = _load_order(db, store_order_id, current_user, "pending")
    order.status = "rejected"
    order.note = body.note if body else None
    order.dispatched_by = current_user["user_id"]
    create_notification(db, order.requested_by, "Store order rejected", f"Store order #{order.store_order_id} was rejected by the warehouse.", "store_order_rejected")
    db.commit()
    return {"store_order_id": order.store_order_id, "status": order.status}


@router.patch("/{store_order_id}/cancel")
def cancel_store_order(
    store_order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("request_store_orders")),
):
    order = _load_order(db, store_order_id, current_user, "pending")
    order.status = "cancelled"
    db.commit()
    return {"store_order_id": order.store_order_id, "status": order.status}


@router.patch("/{store_order_id}/receive")
def receive_store_order(
    store_order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("receive_store_orders")),
):
    order = _load_order(db, store_order_id, current_user, "dispatched")
    product = db.query(Product).filter(Product.product_id == order.product_id).first()
    counter = db.query(CounterInventory).filter(
        CounterInventory.warehouse_id == order.warehouse_id,
        CounterInventory.product_id == order.product_id,
        CounterInventory.batch_id == order.batch_id,
    ).with_for_update().first()
    if counter is None:
        counter = CounterInventory(
            warehouse_id=order.warehouse_id,
            product_id=order.product_id,
            batch_id=order.batch_id,
            quantity=order.quantity,
            minimum_level=product.reorder_level if product else 0,
            unit_price=product.price if product else 0,
            last_replenished_at=datetime.utcnow(),
        )
        db.add(counter)
    else:
        counter.quantity += order.quantity
        counter.last_replenished_at = datetime.utcnow()
    order.status = "received"
    order.received_by = current_user["user_id"]
    order.received_at = datetime.utcnow()
    log_activity(db, current_user["user_id"], current_user["username"], "STORE_ORDER_RECEIVED", f"Store received order #{order.store_order_id} (serial {order.serial_number}).")
    db.commit()
    return {"store_order_id": order.store_order_id, "status": order.status}
