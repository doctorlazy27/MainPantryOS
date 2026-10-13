from datetime import date, datetime
from uuid import uuid4

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.database import get_db
from app.models.batch import Batch
from app.models.boxed_unit import BoxedUnit
from app.models.counter_allocation import CounterAllocation
from app.models.counter_inventory import CounterInventory
from app.models.counter_sale import CounterSale, CounterSaleItem
from app.models.inventory import Inventory
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.schemas.counter import CheckoutCreate, CounterAllocationCreate
from app.services.activity import log_activity
from app.services.expiry import process_expiry
from app.services.inventory_guard import require_available_batch
from app.services.notification import create_notification, notify_roles
from app.services.ai_assistant import answer_warehouse_question
from app.services.ai_provider import AIProviderError
from app.services.order_reservations import available_quantity

router = APIRouter(prefix="/counter", tags=["Counter"])
logger = logging.getLogger(__name__)


def _counter_row(db: Session, row: CounterInventory):
    product = db.query(Product).filter(Product.product_id == row.product_id).first()
    batch = db.query(Batch).filter(Batch.batch_id == row.batch_id).first()
    status = "OUT OF STOCK" if row.quantity <= 0 else "CRITICAL" if row.quantity <= max(1, row.minimum_level // 2) else "LOW" if row.quantity < row.minimum_level else "GOOD"
    return {
        "counter_inventory_id": row.counter_inventory_id,
        "product_id": row.product_id,
        "product_name": product.name if product else "Unknown",
        "category": product.category if product else "General",
        "batch_id": row.batch_id,
        "batch_number": batch.batch_number if batch else "Unknown",
        "quantity": row.quantity,
        "minimum_level": row.minimum_level,
        "unit_price": row.unit_price,
        "expiry_date": batch.expiry_date if batch else None,
        "status": status,
        "last_replenished_at": row.last_replenished_at,
    }


def _checkout_result(db: Session, sale: CounterSale, duplicate: bool):
    item = db.query(CounterSaleItem).filter(CounterSaleItem.sale_id == sale.sale_id).order_by(CounterSaleItem.sale_item_id.asc()).first()
    product = db.query(Product).filter(Product.product_id == item.product_id).first() if item else None
    remaining = db.query(CounterInventory.quantity).filter(
        CounterInventory.warehouse_id == sale.warehouse_id,
        CounterInventory.product_id == item.product_id,
        CounterInventory.batch_id == item.batch_id,
    ).scalar() if item else None
    return {
        "sale_id": sale.sale_id,
        "bill_number": sale.bill_number,
        "total_amount": sale.total_amount,
        "created_at": sale.created_at,
        "product_name": product.name if product else "Unknown product",
        "remaining_quantity": int(remaining or 0),
        "duplicate": duplicate,
    }


@router.get("/inventory")
def get_counter_inventory(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_counter_inventory"))):
    process_expiry(db)
    rows = db.query(CounterInventory).filter(CounterInventory.warehouse_id == current_user.get("warehouse_id")).all()
    return {"inventory": [_counter_row(db, row) for row in rows]}


@router.get("/allocations")
def get_counter_allocations(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_counter_inventory"))):
    rows = db.query(CounterAllocation).filter(CounterAllocation.warehouse_id == current_user.get("warehouse_id")).order_by(CounterAllocation.created_at.desc()).limit(100).all()
    return {"allocations": [{
        "allocation_id": row.allocation_id,
        "product_id": row.product_id,
        "product_name": db.query(Product.name).filter(Product.product_id == row.product_id).scalar(),
        "quantity": row.quantity,
        "status": row.status,
        "created_at": row.created_at,
    } for row in rows]}


@router.post("/allocations")
def request_counter_allocation(request: CounterAllocationCreate, db: Session = Depends(get_db), current_user: dict = Depends(require_permission("request_counter_allocation"))):
    if db.query(Product).filter(Product.product_id == request.product_id).first() is None:
        raise HTTPException(status_code=404, detail="Product not found")
    item = CounterAllocation(product_id=request.product_id, quantity=request.quantity, warehouse_id=current_user.get("warehouse_id"), requested_by=current_user["user_id"])
    db.add(item)
    db.flush()
    if current_user["role"] == "manager":
        return approve_counter_allocation(item.allocation_id, db, current_user)
    notify_roles(db, {"manager"}, "Counter replenishment required", f"Counter allocation request #{item.allocation_id} needs approval.", "counter_replenishment", current_user.get("warehouse_id"))
    db.commit()
    return {"allocation_id": item.allocation_id, "status": item.status}


@router.patch("/allocations/{allocation_id}/approve")
def approve_counter_allocation(allocation_id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_permission("approve_counter_allocation"))):
    allocation = db.query(CounterAllocation).filter(CounterAllocation.allocation_id == allocation_id, CounterAllocation.warehouse_id == current_user.get("warehouse_id"), CounterAllocation.status == "pending").with_for_update().first()
    if allocation is None:
        raise HTTPException(status_code=404, detail="Pending counter allocation not found")
    remaining = allocation.quantity
    warehouse_rows = db.query(Inventory, Batch).join(Batch, Inventory.batch_id == Batch.batch_id).filter(Inventory.warehouse_id == allocation.warehouse_id, Inventory.product_id == allocation.product_id, Inventory.quantity > 0, Inventory.putaway_status == "confirmed", Batch.status == "active", Batch.expiry_date > date.today()).order_by(Batch.expiry_date.asc()).with_for_update().all()
    if sum(available_quantity(db, row) for row, _ in warehouse_rows) < remaining:
        raise HTTPException(status_code=400, detail="Not enough valid warehouse stock for this allocation")
    for warehouse_row, batch in warehouse_rows:
        if remaining <= 0:
            break
        require_available_batch(db, batch.batch_id)
        moved = min(remaining, available_quantity(db, warehouse_row))
        if moved <= 0:
            continue
        warehouse_row.quantity -= moved
        counter = db.query(CounterInventory).filter(CounterInventory.warehouse_id == allocation.warehouse_id, CounterInventory.product_id == allocation.product_id, CounterInventory.batch_id == batch.batch_id).with_for_update().first()
        if counter is None:
            product = db.query(Product).filter(Product.product_id == allocation.product_id).first()
            counter = CounterInventory(warehouse_id=allocation.warehouse_id, product_id=allocation.product_id, batch_id=batch.batch_id, quantity=moved, minimum_level=product.reorder_level if product else 0, unit_price=product.price if product else 0, last_replenished_at=datetime.utcnow())
            db.add(counter)
        else:
            counter.quantity += moved
            counter.last_replenished_at = datetime.utcnow()
        db.add(InventoryMovement(inventory_id=warehouse_row.inventory_id, product_id=allocation.product_id, batch_id=batch.batch_id, warehouse_id=allocation.warehouse_id, movement_type="TRANSFER_TO_COUNTER", event_key=f"counter_allocation:{allocation_id}:{batch.batch_id}", quantity=moved, actor_id=current_user["user_id"], actor_name=current_user["username"], reason=f"Counter allocation #{allocation_id} approved."))
        remaining -= moved
    allocation.status = "approved"
    allocation.reviewed_by = current_user["user_id"]
    allocation.reviewed_at = datetime.utcnow()
    log_activity(db, current_user["user_id"], current_user["username"], "COUNTER_ALLOCATION_APPROVED", f"Approved counter allocation #{allocation_id}.")
    db.commit()
    return {"allocation_id": allocation_id, "status": allocation.status, "message": "Stock transferred to counter using FEFO"}


@router.patch("/allocations/{allocation_id}/reject")
def reject_counter_allocation(allocation_id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_permission("approve_counter_allocation"))):
    allocation = db.query(CounterAllocation).filter(
        CounterAllocation.allocation_id == allocation_id,
        CounterAllocation.warehouse_id == current_user.get("warehouse_id"),
        CounterAllocation.status == "pending",
    ).with_for_update().first()
    if allocation is None:
        raise HTTPException(status_code=404, detail="Pending counter allocation not found")
    allocation.status = "rejected"
    allocation.reviewed_by = current_user["user_id"]
    allocation.reviewed_at = datetime.utcnow()
    create_notification(db, allocation.requested_by, "Counter replenishment rejected", f"Counter allocation #{allocation_id} was rejected.", "counter_replenishment_rejected")
    log_activity(db, current_user["user_id"], current_user["username"], "COUNTER_ALLOCATION_REJECTED", f"Rejected counter allocation #{allocation_id}.")
    db.commit()
    return {"allocation_id": allocation_id, "status": allocation.status}


@router.post("/checkout")
def checkout(checkout: CheckoutCreate, db: Session = Depends(get_db), current_user: dict = Depends(require_permission("checkout_counter"))):
    request_key = checkout.request_key or str(uuid4())
    previous_sale = db.query(CounterSale).filter(
        CounterSale.worker_id == current_user["user_id"],
        CounterSale.request_key == request_key,
    ).first()
    if previous_sale is not None:
        return _checkout_result(db, previous_sale, True)
    process_expiry(db)
    warehouse_id = current_user.get("warehouse_id")
    prepared = []
    total = 0.0
    for requested in checkout.items:
        match = db.query(CounterInventory, Product, Batch, BoxedUnit, Inventory).join(Product, CounterInventory.product_id == Product.product_id).join(Batch, CounterInventory.batch_id == Batch.batch_id).join(Inventory, (Inventory.product_id == CounterInventory.product_id) & (Inventory.batch_id == CounterInventory.batch_id) & (Inventory.warehouse_id == CounterInventory.warehouse_id)).join(BoxedUnit, BoxedUnit.inventory_id == Inventory.inventory_id).filter(CounterInventory.warehouse_id == warehouse_id, CounterInventory.quantity >= requested.quantity, Inventory.putaway_status == "confirmed", Batch.status == "active", Batch.expiry_date > date.today(), (BoxedUnit.scanned_code == requested.scanned_code) | (BoxedUnit.box_code == requested.scanned_code)).order_by(Batch.expiry_date.asc()).with_for_update().first()
        if match is None:
            known = db.query(CounterInventory.quantity).join(Batch, CounterInventory.batch_id == Batch.batch_id).join(Inventory, (Inventory.product_id == CounterInventory.product_id) & (Inventory.batch_id == CounterInventory.batch_id) & (Inventory.warehouse_id == CounterInventory.warehouse_id)).join(BoxedUnit, BoxedUnit.inventory_id == Inventory.inventory_id).filter(CounterInventory.warehouse_id == warehouse_id, (BoxedUnit.scanned_code == requested.scanned_code) | (BoxedUnit.box_code == requested.scanned_code)).order_by(Batch.expiry_date.asc()).first()
            if known is not None and known[0] <= 0:
                raise HTTPException(status_code=400, detail="Out of counter stock")
            raise HTTPException(status_code=404, detail="Product not found at counter")
        counter, product, batch, boxed_unit, warehouse_inventory = match
        prepared.append((counter, product, batch, warehouse_inventory, boxed_unit, requested.quantity))
        total += requested.quantity * product.price
    quantities_by_counter = {}
    quantities_by_boxed_unit = {}
    for counter, _, _, _, boxed_unit, quantity in prepared:
        quantities_by_counter[counter.counter_inventory_id] = (counter, quantities_by_counter.get(counter.counter_inventory_id, (counter, 0))[1] + quantity)
        quantities_by_boxed_unit[boxed_unit.boxed_unit_id] = (boxed_unit, quantities_by_boxed_unit.get(boxed_unit.boxed_unit_id, (boxed_unit, 0))[1] + quantity)
    for counter, quantity in quantities_by_counter.values():
        if counter.quantity < quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient counter stock for product {counter.product_id}")
    for boxed_unit, quantity in quantities_by_boxed_unit.values():
        if boxed_unit.remaining_units < quantity:
            raise HTTPException(status_code=400, detail=f"Barcode has only {boxed_unit.remaining_units} units remaining")
    sale = CounterSale(warehouse_id=warehouse_id, bill_number=f"INV-{datetime.utcnow():%Y%m%d%H%M%S}-{uuid4().hex[:4].upper()}", total_amount=total, worker_id=current_user["user_id"], request_key=request_key)
    db.add(sale)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        duplicate_sale = db.query(CounterSale).filter(
            CounterSale.worker_id == current_user["user_id"],
            CounterSale.request_key == request_key,
        ).first()
        if duplicate_sale is None:
            raise
        return _checkout_result(db, duplicate_sale, True)
    for counter, product, batch, warehouse_inventory, boxed_unit, quantity in prepared:
        counter.quantity -= quantity
        boxed_unit.remaining_units -= quantity
        db.add(CounterSaleItem(sale_id=sale.sale_id, product_id=product.product_id, batch_id=batch.batch_id, quantity=quantity, unit_price=product.price, line_total=quantity * product.price))
        db.add(InventoryMovement(inventory_id=warehouse_inventory.inventory_id, product_id=product.product_id, batch_id=batch.batch_id, warehouse_id=warehouse_id, movement_type="SOLD_COUNTER", event_key=f"counter_sale:{sale.sale_id}:{product.product_id}:{batch.batch_id}", quantity=quantity, actor_id=current_user["user_id"], actor_name=current_user["username"], reason=f"Counter checkout {sale.bill_number}."))
        if counter.quantity < counter.minimum_level:
            notify_roles(db, {"manager"}, "Counter stock low", f"Counter stock for {product.name} is {counter.quantity}; minimum is {counter.minimum_level}.", "counter_low_stock", warehouse_id)
    log_activity(db, current_user["user_id"], current_user["username"], "COUNTER_CHECKOUT", f"Generated bill {sale.bill_number} for {total:.2f}.")
    db.commit()
    return _checkout_result(db, sale, False)


@router.get("/sales")
def get_counter_sales(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_counter_sales"))):
    rows = db.query(CounterSale).filter(CounterSale.warehouse_id == current_user.get("warehouse_id")).order_by(CounterSale.created_at.desc()).limit(100).all()
    return {"sales": [{"sale_id": row.sale_id, "bill_number": row.bill_number, "total_amount": row.total_amount, "worker_id": row.worker_id, "created_at": row.created_at} for row in rows]}


@router.get("/lookup")
def lookup_counter_barcode(barcode: str, db: Session = Depends(get_db), current_user: dict = Depends(require_permission("checkout_counter"))):
    row = db.query(CounterInventory, Product, Batch, BoxedUnit).join(Product, CounterInventory.product_id == Product.product_id).join(Batch, CounterInventory.batch_id == Batch.batch_id).join(Inventory, (Inventory.product_id == CounterInventory.product_id) & (Inventory.batch_id == CounterInventory.batch_id) & (Inventory.warehouse_id == CounterInventory.warehouse_id)).join(BoxedUnit, BoxedUnit.inventory_id == Inventory.inventory_id).filter(CounterInventory.warehouse_id == current_user.get("warehouse_id"), Inventory.putaway_status == "confirmed", Batch.status == "active", (BoxedUnit.scanned_code == barcode) | (BoxedUnit.box_code == barcode)).order_by(Batch.expiry_date.asc()).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found at counter")
    counter, product, batch, _ = row
    if batch.expiry_date <= date.today():
        raise HTTPException(status_code=400, detail="This product batch has expired")
    if counter.quantity <= 0:
        raise HTTPException(status_code=400, detail="Out of counter stock")
    return {"product_name": product.name, "unit_price": product.price, "available_quantity": counter.quantity, "expiry_date": batch.expiry_date, "batch_number": batch.batch_number}


@router.get("/copilot")
def warehouse_copilot(question: str = Query(default="What needs attention today?", max_length=500), db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_ai_copilot"))):
    process_expiry(db)
    counter = db.query(CounterInventory).filter(CounterInventory.warehouse_id == current_user.get("warehouse_id")).all()
    low = [_counter_row(db, row) for row in counter if row.quantity < row.minimum_level]
    priorities = [f"Counter {item['product_name']} is {item['quantity']} units below its minimum." for item in low]
    expiring = db.query(Product.name, Batch.batch_number, Batch.expiry_date).join(Batch, Product.product_id == Batch.product_id).join(Inventory, Inventory.batch_id == Batch.batch_id).filter(Inventory.warehouse_id == current_user.get("warehouse_id"), Batch.expiry_date > date.today()).order_by(Batch.expiry_date.asc()).limit(5).all()
    priorities.extend([f"{name} batch {batch} expires on {expiry.isoformat()}." for name, batch, expiry in expiring])
    if not priorities:
        priorities.append("No urgent counter or expiry risks are currently reported.")
    fallback_answer = f"For '{question}', I found {len(low)} counter replenishment item(s) and {len(expiring)} upcoming expiry item(s) in live warehouse data."
    context = {
        "counter_low_stock": low,
        "upcoming_expiry": [{"product_name": name, "batch_number": batch, "expiry_date": expiry.isoformat()} for name, batch, expiry in expiring],
        "priorities": priorities[:6],
    }
    answer = None
    try:
        answer = answer_warehouse_question(question, context)
    except AIProviderError:
        logger.exception("AI copilot unavailable for warehouse %s", current_user.get("warehouse_id"))
    return {"answer": answer or fallback_answer, "priorities": priorities[:6], "ai_powered": bool(answer)}