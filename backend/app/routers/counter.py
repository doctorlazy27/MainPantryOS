from datetime import date, datetime
from uuid import uuid4

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.database import get_db
from app.models.batch import Batch
from app.models.counter_inventory import CounterInventory
from app.models.counter_sale import CounterSale, CounterSaleItem
from app.models.inventory import Inventory
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.user import User
from app.schemas.counter import CheckoutCreate, CounterMinimumUpdate
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
        "serial_number": (batch.serial_number if batch else None) or (product.serial_number if product else None),
        "quantity": row.quantity,
        "minimum_level": row.minimum_level,
        "unit_price": row.unit_price,
        "expiry_date": batch.expiry_date if batch else None,
        "status": status,
        "last_replenished_at": row.last_replenished_at,
    }


def _sale_payload(db: Session, sale: CounterSale, duplicate: bool = False):
    rows = db.query(CounterSaleItem, Product, Batch).join(
        Product, CounterSaleItem.product_id == Product.product_id
    ).join(Batch, CounterSaleItem.batch_id == Batch.batch_id).filter(
        CounterSaleItem.sale_id == sale.sale_id
    ).order_by(CounterSaleItem.sale_item_id.asc()).all()
    lines: dict[int, dict] = {}
    for item, product, batch in rows:
        line = lines.setdefault(product.product_id, {
            "product_id": product.product_id,
            "product_name": product.name,
            "serial_number": batch.serial_number or product.serial_number,
            "quantity": 0,
            "unit_price": item.unit_price,
            "line_total": 0.0,
        })
        line["quantity"] += item.quantity
        line["line_total"] = round(line["line_total"] + item.line_total, 2)
    return {
        "sale_id": sale.sale_id,
        "bill_number": sale.bill_number,
        "total_amount": sale.total_amount,
        "worker_id": sale.worker_id,
        "cashier_name": db.query(User.full_name).filter(User.user_id == sale.worker_id).scalar(),
        "created_at": sale.created_at,
        "items": list(lines.values()),
        "duplicate": duplicate,
    }


def _counter_rows_for_serial(db: Session, warehouse_id: int | None, serial: str, lock: bool = False):
    query = db.query(CounterInventory, Product, Batch).join(
        Product, CounterInventory.product_id == Product.product_id
    ).join(Batch, CounterInventory.batch_id == Batch.batch_id).filter(
        CounterInventory.warehouse_id == warehouse_id,
        Batch.serial_number == serial,
    ).order_by(Batch.expiry_date.asc(), CounterInventory.counter_inventory_id.asc())
    return query.with_for_update().all() if lock else query.all()


def _sellable(rows):
    return [
        (counter, product, batch) for counter, product, batch in rows
        if counter.quantity > 0 and batch.status == "active" and batch.expiry_date > date.today()
    ]


@router.get("/inventory")
def get_counter_inventory(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_counter_inventory"))):
    process_expiry(db)
    rows = db.query(CounterInventory).filter(CounterInventory.warehouse_id == current_user.get("warehouse_id")).all()
    return {"inventory": [_counter_row(db, row) for row in rows]}


@router.patch("/minimum")
def set_counter_minimum(body: CounterMinimumUpdate, db: Session = Depends(get_db), current_user: dict = Depends(require_permission("request_store_orders"))):
    product = db.query(Product).filter(Product.product_id == body.product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    product.reorder_level = body.minimum_level
    db.query(CounterInventory).filter(
        CounterInventory.warehouse_id == current_user.get("warehouse_id"),
        CounterInventory.product_id == body.product_id,
    ).update({CounterInventory.minimum_level: body.minimum_level}, synchronize_session=False)
    db.commit()
    return {"product_id": body.product_id, "minimum_level": body.minimum_level}


@router.post("/checkout")
def checkout(checkout: CheckoutCreate, db: Session = Depends(get_db), current_user: dict = Depends(require_permission("checkout_counter"))):
    request_key = checkout.request_key or str(uuid4())
    previous_sale = db.query(CounterSale).filter(
        CounterSale.worker_id == current_user["user_id"],
        CounterSale.request_key == request_key,
    ).first()
    if previous_sale is not None:
        return _sale_payload(db, previous_sale, True)
    process_expiry(db)
    warehouse_id = current_user.get("warehouse_id")
    wanted: dict[str, int] = {}
    for requested in checkout.items:
        code = requested.scanned_code.strip()
        wanted[code] = wanted.get(code, 0) + requested.quantity

    allocations = []
    total = 0.0
    for code, quantity in wanted.items():
        rows = _counter_rows_for_serial(db, warehouse_id, code, lock=True)
        if not rows:
            raise HTTPException(status_code=404, detail=f"Serial number {code} was not found at the counter")
        sellable = _sellable(rows)
        available = sum(counter.quantity for counter, _product, _batch in sellable)
        if available <= 0:
            raise HTTPException(status_code=400, detail=f"{rows[0][1].name} is out of counter stock")
        if available < quantity:
            raise HTTPException(status_code=400, detail=f"Only {available} units of {rows[0][1].name} are available at the counter")
        remaining = quantity
        for counter, product, batch in sellable:
            take = min(counter.quantity, remaining)
            allocations.append((counter, product, batch, take))
            total += take * product.price
            remaining -= take
            if remaining == 0:
                break

    sale = CounterSale(warehouse_id=warehouse_id, bill_number=f"INV-{datetime.utcnow():%Y%m%d%H%M%S}-{uuid4().hex[:4].upper()}", total_amount=round(total, 2), worker_id=current_user["user_id"], request_key=request_key)
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
        return _sale_payload(db, duplicate_sale, True)
    for counter, product, batch, quantity in allocations:
        counter.quantity -= quantity
        db.add(CounterSaleItem(sale_id=sale.sale_id, product_id=product.product_id, batch_id=batch.batch_id, quantity=quantity, unit_price=product.price, line_total=round(quantity * product.price, 2)))
        warehouse_inventory = db.query(Inventory).filter(
            Inventory.product_id == product.product_id,
            Inventory.batch_id == batch.batch_id,
            Inventory.warehouse_id == warehouse_id,
        ).first()
        if warehouse_inventory is not None:
            db.add(InventoryMovement(inventory_id=warehouse_inventory.inventory_id, product_id=product.product_id, batch_id=batch.batch_id, warehouse_id=warehouse_id, movement_type="SOLD_COUNTER", event_key=f"counter_sale:{sale.sale_id}:{product.product_id}:{batch.batch_id}", quantity=quantity, actor_id=current_user["user_id"], actor_name=current_user["username"], reason=f"Counter checkout {sale.bill_number}."))
        if counter.quantity < counter.minimum_level:
            notify_roles(db, {"manager"}, "Counter stock low", f"Counter stock for {product.name} is {counter.quantity}; minimum is {counter.minimum_level}.", "counter_low_stock", warehouse_id)
    log_activity(db, current_user["user_id"], current_user["username"], "COUNTER_CHECKOUT", f"Generated bill {sale.bill_number} for {total:.2f}.")
    db.commit()
    return _sale_payload(db, sale, False)


@router.get("/sales")
def get_counter_sales(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_counter_sales"))):
    rows = db.query(CounterSale).filter(CounterSale.warehouse_id == current_user.get("warehouse_id")).order_by(CounterSale.created_at.desc()).limit(100).all()
    return {"sales": [_sale_payload(db, row) for row in rows]}


@router.get("/lookup")
def lookup_counter_barcode(barcode: str, db: Session = Depends(get_db), current_user: dict = Depends(require_permission("checkout_counter"))):
    code = barcode.strip()
    rows = _counter_rows_for_serial(db, current_user.get("warehouse_id"), code)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Serial number {code} was not found at the counter")
    sellable = _sellable(rows)
    if not sellable:
        if all(batch.expiry_date <= date.today() for _counter, _product, batch in rows):
            raise HTTPException(status_code=400, detail="This product batch has expired")
        raise HTTPException(status_code=400, detail=f"{rows[0][1].name} is out of counter stock")
    _counter, product, batch = sellable[0]
    return {
        "serial_number": code,
        "product_id": product.product_id,
        "product_name": product.name,
        "unit_price": product.price,
        "available_quantity": sum(counter.quantity for counter, _p, _b in sellable),
        "expiry_date": batch.expiry_date,
        "batch_number": batch.batch_number,
    }


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
