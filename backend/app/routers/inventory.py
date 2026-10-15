from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.inventory import Inventory
from app.schemas.inventory import InventoryCreate
from app.auth.dependencies import require_permission
from datetime import date, datetime, timedelta

from app.models.batch import Batch
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.models.inventory_addition_request import InventoryAdditionRequest
from app.models.boxed_unit import BoxedUnit
from app.models.inventory_movement import InventoryMovement
from app.models.temperature_log import TemperatureLog
from app.models.order_pick_scan import OrderPickScan
from app.models.counter_inventory import CounterInventory
from app.models.order import SalesOrder
from app.models.order_item import SalesOrderItem
from app.models.order_inventory_reservation import OrderInventoryReservation
from app.schemas.inventory_addition_request import InventoryAdditionRequestCreate
from app.schemas.inventory_addition_approval import InventoryReceiptDetails
from app.services.serial import name_equals, register_product_serial
from app.schemas.inventory_scan import InventoryScan
from app.schemas.warehouse_workflow import BatchStatusUpdate, PutawayConfirm, TemperatureCheckCreate
from app.services.activity import log_activity
from app.services.notification import create_notification, notify_roles
from app.services.boxed_units import create_boxed_units
from app.services.expiry import process_expiry
from app.services.inventory_guard import require_available_batch
from app.services.cold_chain import temperature_is_safe, temperature_range
from app.services.order_reservations import available_quantity, release_batch_reservations


router = APIRouter(
    prefix="/inventory",
    tags=["Inventory"]
)


@router.get("/putaway-queue")
def list_putaway_queue(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory")),
):
    rows = db.query(Inventory, Batch, Product).join(
        Batch, Inventory.batch_id == Batch.batch_id
    ).join(Product, Inventory.product_id == Product.product_id).filter(
        Inventory.warehouse_id == current_user.get("warehouse_id"),
        Inventory.putaway_status == "pending",
        Batch.status == "active",
    ).order_by(Batch.expiry_date.asc()).all()
    return {"items": [{
        "inventory_id": inventory.inventory_id,
        "product_name": product.name,
        "batch_number": batch.batch_number,
        "quantity": inventory.quantity,
        "storage_zone": inventory.storage_zone,
        "expiry_date": batch.expiry_date,
    } for inventory, batch, product in rows]}


@router.patch("/{inventory_id}/putaway")
def confirm_putaway(
    inventory_id: int,
    request: PutawayConfirm,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("update_inventory")),
):
    inventory = db.query(Inventory).filter(
        Inventory.inventory_id == inventory_id,
        Inventory.warehouse_id == current_user.get("warehouse_id"),
    ).with_for_update().first()
    if inventory is None:
        raise HTTPException(status_code=404, detail="Staged inventory not found")
    batch = db.query(Batch).filter(Batch.batch_id == inventory.batch_id).with_for_update().first()
    if batch is None or batch.status != "active":
        raise HTTPException(status_code=409, detail="Only QC-approved batches can be put away")
    if inventory.putaway_status != "pending":
        raise HTTPException(status_code=409, detail="Inventory is not waiting for putaway")
    if request.storage_zone != inventory.storage_zone:
        raise HTTPException(status_code=400, detail="Scanned zone does not match the receiving zone")
    location_code = request.location_code.strip().upper()
    if location_code in {"STAGING", "QUARANTINE"}:
        raise HTTPException(status_code=400, detail="Scan a final shelf or bin location")
    inventory.location_code = location_code
    inventory.putaway_status = "confirmed"
    log_activity(db, current_user["user_id"], current_user["username"], "PUTAWAY_CONFIRMED", f"Put away inventory #{inventory_id} at {request.storage_zone}/{location_code}.")
    db.commit()
    return {"inventory_id": inventory_id, "storage_zone": inventory.storage_zone, "location_code": location_code, "putaway_status": inventory.putaway_status}


@router.post("/batches/{batch_id}/temperature")
def record_storage_temperature(
    batch_id: int,
    reading: TemperatureCheckCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("update_inventory")),
):
    inventory = db.query(Inventory).filter(
        Inventory.batch_id == batch_id,
        Inventory.warehouse_id == current_user.get("warehouse_id"),
    ).with_for_update().first()
    if inventory is None:
        raise HTTPException(status_code=404, detail="Batch inventory not found in this warehouse")
    batch = db.query(Batch).filter(Batch.batch_id == batch_id).with_for_update().first()
    allowed = temperature_range(inventory.storage_zone)
    within_range = temperature_is_safe(inventory.storage_zone, reading.temperature_c)
    db.add(TemperatureLog(
        batch_id=batch_id,
        inventory_id=inventory.inventory_id,
        warehouse_id=inventory.warehouse_id,
        recorded_by=current_user["user_id"],
        stage="storage",
        storage_zone=inventory.storage_zone,
        temperature_c=reading.temperature_c,
        minimum_c=allowed.minimum_c,
        maximum_c=allowed.maximum_c,
        within_range=within_range,
    ))
    if not within_range:
        batch.status = "quarantined"
        db.query(Inventory).filter(Inventory.batch_id == batch_id, Inventory.warehouse_id == inventory.warehouse_id).update({Inventory.putaway_status: "hold", Inventory.location_code: "QUARANTINE"}, synchronize_session="fetch")
        pending_orders = db.query(SalesOrder.order_id).filter(SalesOrder.status == "approved", SalesOrder.warehouse_id == inventory.warehouse_id).subquery()
        db.query(OrderPickScan).filter(OrderPickScan.batch_id == batch_id, OrderPickScan.order_id.in_(pending_orders)).update({OrderPickScan.is_valid: False}, synchronize_session=False)
        release_batch_reservations(db, batch_id, inventory.warehouse_id)
        db.query(CounterInventory).filter(CounterInventory.batch_id == batch_id, CounterInventory.warehouse_id == inventory.warehouse_id).update({CounterInventory.quantity: 0}, synchronize_session=False)
        notify_roles(db, {"manager"}, "Cold-chain exception", f"Batch {batch.batch_number} measured {reading.temperature_c} C outside the {inventory.storage_zone.lower()} range and was quarantined.", "cold_chain_exception", inventory.warehouse_id)
    log_activity(db, current_user["user_id"], current_user["username"], "TEMPERATURE_RECORDED", f"Recorded {reading.temperature_c} C for batch {batch.batch_number}; within range: {within_range}.")
    db.commit()
    return {"batch_id": batch_id, "temperature_c": reading.temperature_c, "within_range": within_range, "batch_status": batch.status}


@router.get("/temperature-logs")
def list_temperature_logs(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory")),
):
    rows = db.query(TemperatureLog).filter(
        TemperatureLog.warehouse_id == current_user.get("warehouse_id")
    ).order_by(TemperatureLog.recorded_at.desc()).limit(100).all()
    return {"logs": [{
        "temperature_log_id": row.temperature_log_id,
        "batch_id": row.batch_id,
        "inventory_id": row.inventory_id,
        "stage": row.stage,
        "storage_zone": row.storage_zone,
        "temperature_c": row.temperature_c,
        "minimum_c": row.minimum_c,
        "maximum_c": row.maximum_c,
        "within_range": row.within_range,
        "recorded_at": row.recorded_at,
    } for row in rows]}


@router.get("/reports/operations")
def get_operational_metrics(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory_recommendations")),
):
    warehouse_id = current_user.get("warehouse_id")
    cutoff = datetime.utcnow() - timedelta(days=30)
    movement_rows = db.query(
        InventoryMovement.movement_type,
        func.coalesce(func.sum(InventoryMovement.quantity), 0),
    ).filter(
        InventoryMovement.warehouse_id == warehouse_id,
        InventoryMovement.created_at >= cutoff,
    ).group_by(InventoryMovement.movement_type).all()
    movement_totals = {movement_type: int(quantity) for movement_type, quantity in movement_rows}
    stock_on_hand = int(db.query(func.coalesce(func.sum(Inventory.quantity), 0)).join(
        Batch, Inventory.batch_id == Batch.batch_id
    ).filter(
        Inventory.warehouse_id == warehouse_id,
        Batch.status == "active",
        Inventory.putaway_status == "confirmed",
    ).scalar() or 0)
    required_units = int(db.query(func.coalesce(func.sum(SalesOrderItem.quantity), 0)).join(
        SalesOrder, SalesOrderItem.order_id == SalesOrder.order_id
    ).filter(
        SalesOrder.warehouse_id == warehouse_id,
        SalesOrder.status == "fulfilled",
        SalesOrder.created_at >= cutoff,
    ).scalar() or 0)
    verified_units = int(db.query(func.coalesce(func.sum(OrderPickScan.quantity), 0)).join(
        SalesOrder, OrderPickScan.order_id == SalesOrder.order_id
    ).filter(
        SalesOrder.warehouse_id == warehouse_id,
        SalesOrder.status == "fulfilled",
        OrderPickScan.is_valid == True,
        OrderPickScan.created_at >= cutoff,
    ).scalar() or 0)
    sold_units = movement_totals.get("SOLD", 0) + movement_totals.get("SOLD_COUNTER", 0)
    expired_units = movement_totals.get("EXPIRED", 0) + movement_totals.get("COUNTER_EXPIRED", 0)
    disposed_units = movement_totals.get("DISPOSED", 0)
    donated_units = movement_totals.get("DONATED", 0)
    return {
        "period_days": 30,
        "sold_units": sold_units,
        "current_saleable_stock": stock_on_hand,
        "stock_turn_rate": round(sold_units / stock_on_hand, 2) if stock_on_hand else None,
        "fefo_verified_units": verified_units,
        "fulfilled_units": required_units,
        "fefo_compliance_percent": round(verified_units / required_units * 100, 1) if required_units else None,
        "expired_units": expired_units,
        "disposed_units": disposed_units,
        "donated_units": donated_units,
        "waste_units": expired_units + disposed_units,
    }


@router.patch("/batches/{batch_id}/status")
def update_batch_status(
    batch_id: int,
    update: BatchStatusUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("approve_inventory_requests")),
):
    batch = db.query(Batch).filter(Batch.batch_id == batch_id).with_for_update().first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    rows = db.query(Inventory).filter(
        Inventory.batch_id == batch_id,
        Inventory.warehouse_id == current_user.get("warehouse_id"),
    ).with_for_update().all()
    if not rows:
        raise HTTPException(status_code=404, detail="Batch is not assigned to your warehouse")
    if batch.status in {"expired", "disposed", "donated"}:
        raise HTTPException(status_code=409, detail="Expired or disposed batches cannot be reopened")
    if update.status == "active" and batch.status != "quarantined":
        raise HTTPException(status_code=409, detail="Only quarantined batches can be released")
    if update.status in {"disposed", "donated"} and batch.status not in {"active", "quarantined"}:
        raise HTTPException(status_code=409, detail="Batch cannot be disposed from its current status")
    batch.status = update.status
    for inventory in rows:
        if update.status == "quarantined":
            inventory.putaway_status = "hold"
            inventory.location_code = "QUARANTINE"
        elif update.status == "active":
            inventory.putaway_status = "pending"
            inventory.location_code = "STAGING"
        elif update.status in {"disposed", "donated"} and inventory.quantity:
            disposed_quantity = inventory.quantity
            inventory.quantity = 0
            db.add(InventoryMovement(
                inventory_id=inventory.inventory_id,
                product_id=inventory.product_id,
                batch_id=batch_id,
                warehouse_id=inventory.warehouse_id,
                movement_type="DONATED" if update.status == "donated" else "DISPOSED",
                quantity=disposed_quantity,
                actor_id=current_user["user_id"],
                actor_name=current_user["username"],
                reason=update.reason,
            ))
    if update.status != "active":
        pending_orders = db.query(SalesOrder.order_id).filter(SalesOrder.status == "approved", SalesOrder.warehouse_id == current_user.get("warehouse_id")).subquery()
        db.query(OrderPickScan).filter(OrderPickScan.batch_id == batch_id, OrderPickScan.order_id.in_(pending_orders)).update({OrderPickScan.is_valid: False}, synchronize_session=False)
        release_batch_reservations(db, batch_id, current_user.get("warehouse_id"))
        db.query(CounterInventory).filter(CounterInventory.batch_id == batch_id, CounterInventory.warehouse_id == current_user.get("warehouse_id")).update({CounterInventory.quantity: 0}, synchronize_session=False)
    log_activity(db, current_user["user_id"], current_user["username"], "BATCH_STATUS_UPDATED", f"Batch {batch.batch_number} marked {update.status}: {update.reason}")
    db.commit()
    return {"batch_id": batch_id, "status": batch.status}


@router.get("/addition-requests")
def list_addition_requests(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory")),
):
    query = db.query(InventoryAdditionRequest).filter(
        InventoryAdditionRequest.warehouse_id == current_user.get("warehouse_id")
    )
    rows = query.order_by(InventoryAdditionRequest.created_at.desc()).all()
    return {
        "requests": [
            {
                "request_id": item.request_id,
                "product_id": item.product_id,
                "product_name": db.query(Product.name).filter(Product.product_id == item.product_id).scalar(),
                "category": item.category,
                "quantity": item.quantity,
                "boxed_units": item.boxed_units,
                "units_per_box": item.units_per_box,
                "unit_price": item.unit_price,
                "batch_number": db.query(Batch.batch_number).filter(Batch.batch_id == item.batch_id).scalar(),
                "serial_number": item.serial_number,
                "status": item.status,
                "requested_by": item.requested_by,
                "created_at": item.created_at,
                "reviewed_at": item.reviewed_at,
                "received_at": item.received_at,
            }
            for item in rows
        ]
    }


@router.post("/addition-requests")
def request_inventory_addition(
    request: InventoryAdditionRequestCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("submit_inventory_requests")),
):
    warehouse_id = current_user.get("warehouse_id")
    product = db.query(Product).filter(name_equals(Product.name, request.product_name), Product.warehouse_id == warehouse_id).first()
    quantity = request.boxed_units * request.units_per_box if request.boxed_units else request.quantity
    if product is None:
        product = Product(name=request.product_name.strip(), warehouse_id=warehouse_id, category=request.category, quantity=0, unit="units", price=request.unit_price, units_per_box=request.units_per_box, reorder_level=0)
        db.add(product)
        db.flush()

    item = InventoryAdditionRequest(
        product_id=product.product_id,
        warehouse_id=warehouse_id,
        quantity=quantity,
        category=request.category,
        boxed_units=request.boxed_units,
        units_per_box=request.units_per_box,
        unit_price=request.unit_price,
        box_unit_cost=request.box_unit_cost or request.unit_price * request.units_per_box,
        requested_by=current_user["user_id"],
    )
    db.add(item)
    db.flush()
    notify_roles(db, {"manager"}, "Inventory addition request", f"Request #{item.request_id} needs approval.", "inventory_request", warehouse_id)
    db.commit()
    return {"message": "Inventory addition request submitted", "request_id": item.request_id, "status": item.status}


@router.patch("/addition-requests/{request_id}/approve")
def approve_inventory_addition(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("approve_inventory_requests")),
):
    item = db.query(InventoryAdditionRequest).filter(
        InventoryAdditionRequest.request_id == request_id,
        InventoryAdditionRequest.warehouse_id == current_user.get("warehouse_id"),
        InventoryAdditionRequest.status == "pending",
    ).with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="Pending inventory request not found")
    item.status = "approved"
    item.reviewed_by = current_user["user_id"]
    item.reviewed_at = datetime.utcnow()
    create_notification(db, item.requested_by, "Inventory request approved", f"Inventory request #{item.request_id} was approved. Record the delivery details once the product has been received.", "inventory_request_approved")
    log_activity(db, current_user["user_id"], current_user["username"], "INVENTORY_REQUEST_APPROVED", f"Approved inventory addition request #{item.request_id}.")
    db.commit()
    return {"message": "Inventory addition approved", "request_id": request_id, "status": item.status}


@router.patch("/addition-requests/{request_id}/receive")
def receive_inventory_addition(
    request_id: int,
    approval: InventoryReceiptDetails,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("submit_inventory_requests")),
):
    item = db.query(InventoryAdditionRequest).filter(
        InventoryAdditionRequest.request_id == request_id,
        InventoryAdditionRequest.warehouse_id == current_user.get("warehouse_id"),
        InventoryAdditionRequest.status == "approved",
    ).with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="Manager-approved inventory request not found")
    if approval.expiry_date <= approval.manufacturing_date:
        raise HTTPException(status_code=400, detail="Expiry date must be after manufacturing date")
    if approval.expiry_date <= date.today():
        raise HTTPException(status_code=400, detail="Cannot approve an already expired batch")
    allowed_temperature = temperature_range(approval.storage_zone)
    passed_qc = approval.temperature_c is None or temperature_is_safe(approval.storage_zone, approval.temperature_c)
    product = db.query(Product).filter(Product.product_id == item.product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Requested product not found")
    serial = register_product_serial(db, product, approval.serial_number)
    if db.query(Batch.batch_id).filter(Batch.batch_number == approval.batch_number.strip(), Batch.batch_id != (item.batch_id or 0)).first():
        raise HTTPException(status_code=409, detail=f"Batch number {approval.batch_number.strip()} already exists")
    product.aisle = approval.aisle.strip()
    product.shelf_number = approval.shelf_number.strip()
    shelf_location = f"{product.aisle}-{product.shelf_number}".upper()
    if item.batch_id is None:
        batch = Batch(product_id=item.product_id, serial_number=serial, batch_number=approval.batch_number.strip(), manufacturing_date=approval.manufacturing_date, expiry_date=approval.expiry_date, status="active" if passed_qc else "quarantined")
        db.add(batch)
        db.flush()
        item.batch_id = batch.batch_id
    else:
        batch = db.query(Batch).filter(Batch.batch_id == item.batch_id).with_for_update().first()
        if batch is None:
            raise HTTPException(status_code=404, detail="Requested batch not found")
        batch.serial_number = serial
        batch.batch_number = approval.batch_number.strip()
        batch.manufacturing_date = approval.manufacturing_date
        batch.expiry_date = approval.expiry_date
        if not passed_qc:
            batch.status = "quarantined"
    existing = db.query(Inventory).filter(
        Inventory.product_id == item.product_id,
        Inventory.batch_id == item.batch_id,
        Inventory.warehouse_id == item.warehouse_id,
    ).with_for_update().first()
    if existing:
        inventory = existing
        existing.quantity += item.quantity
        existing.boxed_units += item.boxed_units
        existing.total_box_cost += item.boxed_units * (item.box_unit_cost or item.unit_price * item.units_per_box)
        existing.storage_zone = approval.storage_zone
        existing.location_code = shelf_location if passed_qc else "QUARANTINE"
        existing.putaway_status = "confirmed" if passed_qc and batch.status == "active" else "hold"
        create_boxed_units(db, existing.inventory_id, item.boxed_units, item.units_per_box, item.unit_price)
        db.add(InventoryMovement(
            inventory_id=existing.inventory_id,
            product_id=existing.product_id,
            batch_id=existing.batch_id,
            warehouse_id=existing.warehouse_id,
            movement_type="RECEIVED",
            quantity=item.quantity,
            actor_id=current_user["user_id"],
            actor_name=current_user["username"],
            reason=f"Inventory addition request #{item.request_id} approved and merged.",
        ))
    else:
        box_cost = item.box_unit_cost or item.unit_price * item.units_per_box
        inventory = Inventory(
            product_id=item.product_id,
            batch_id=item.batch_id,
            warehouse_id=item.warehouse_id,
            quantity=item.quantity,
            boxed_units=item.boxed_units,
            units_per_box=item.units_per_box,
            unit_price=item.unit_price,
            box_unit_cost=box_cost,
            total_box_cost=item.boxed_units * box_cost,
            storage_zone=approval.storage_zone,
            location_code=shelf_location if passed_qc else "QUARANTINE",
            putaway_status="confirmed" if passed_qc and batch.status == "active" else "hold",
        )
        db.add(inventory)
        db.flush()
        create_boxed_units(db, inventory.inventory_id, item.boxed_units, item.units_per_box, item.unit_price)
        db.add(InventoryMovement(
            inventory_id=inventory.inventory_id,
            product_id=inventory.product_id,
            batch_id=inventory.batch_id,
            warehouse_id=inventory.warehouse_id,
            movement_type="RECEIVED",
            quantity=inventory.quantity,
            actor_id=current_user["user_id"],
            actor_name=current_user["username"],
            reason=f"Inventory addition request #{item.request_id} approved.",
        ))
    if approval.temperature_c is not None:
        db.add(TemperatureLog(
            batch_id=batch.batch_id,
            inventory_id=inventory.inventory_id,
            warehouse_id=item.warehouse_id,
            recorded_by=current_user["user_id"],
            stage="receiving",
            storage_zone=approval.storage_zone,
            temperature_c=approval.temperature_c,
            minimum_c=allowed_temperature.minimum_c,
            maximum_c=allowed_temperature.maximum_c,
            within_range=passed_qc,
        ))
    if not passed_qc:
        notify_roles(db, {"manager"}, "Cold-chain exception", f"Inventory request #{item.request_id} was received outside the {approval.storage_zone.lower()} temperature range and quarantined.", "cold_chain_exception", item.warehouse_id)
    log_activity(db, current_user["user_id"], current_user["username"], "INVENTORY_RECEIVED", f"Received inventory addition request #{item.request_id}: {item.quantity} units, serial {serial}, batch {batch.batch_number}.")
    item.status = "received"
    item.serial_number = serial
    item.received_by = current_user["user_id"]
    item.received_at = datetime.utcnow()
    notify_roles(db, {"manager"}, "Inventory received", f"Inventory request #{item.request_id} was received with serial {serial} and is now in inventory.", "inventory_request_received", item.warehouse_id)
    db.commit()
    return {"message": "Inventory received and registered", "request_id": request_id, "status": item.status, "serial_number": serial}


@router.patch("/addition-requests/{request_id}/reject")
def reject_inventory_addition(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("approve_inventory_requests")),
):
    item = db.query(InventoryAdditionRequest).filter(
        InventoryAdditionRequest.request_id == request_id,
        InventoryAdditionRequest.warehouse_id == current_user.get("warehouse_id"),
        InventoryAdditionRequest.status.in_(["pending", "approved"]),
    ).with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="Open inventory request not found")
    item.status = "rejected"
    item.reviewed_by = current_user["user_id"]
    item.reviewed_at = datetime.utcnow()
    create_notification(db, item.requested_by, "Inventory request rejected", f"Inventory request #{item.request_id} was rejected.", "inventory_request_rejected")
    db.commit()
    return {"message": "Inventory addition rejected", "request_id": request_id, "status": item.status}


@router.post("/scan-reduction")
def reduce_inventory_by_scan(
    scan: InventoryScan,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("pick_stock")),
):
    event_key = f"barcode_scan:{scan.scan_event_id}"
    previous = db.query(InventoryMovement).filter(InventoryMovement.event_key == event_key).first()
    if previous:
        product = db.query(Product).filter(Product.product_id == previous.product_id).first()
        return {
            "message": "Scan already applied",
            "scan_event_id": scan.scan_event_id,
            "movement_id": previous.movement_id,
            "product_name": product.name if product else "Unknown product",
            "quantity_removed": previous.quantity,
            "remaining_quantity": db.query(Inventory.quantity).filter(Inventory.inventory_id == previous.inventory_id).scalar(),
            "duplicate": True,
        }

    candidates = db.query(Inventory, Product, Batch).join(
        Product, Inventory.product_id == Product.product_id
    ).join(
        Batch, Inventory.batch_id == Batch.batch_id
    ).filter(
        Inventory.warehouse_id == current_user.get("warehouse_id"),
        Inventory.quantity > 0,
        Inventory.putaway_status == "confirmed",
        Batch.status == "active",
        Batch.expiry_date > date.today(),
        Batch.serial_number == scan.scanned_code.strip(),
    ).order_by(Batch.expiry_date.asc(), Inventory.inventory_id.asc()).with_for_update().all()
    if not candidates:
        raise HTTPException(status_code=404, detail="Serial number is not registered with available stock in this warehouse")
    match = next(((inv, prod, bat) for inv, prod, bat in candidates if available_quantity(db, inv) >= scan.quantity), None)
    if match is None:
        raise HTTPException(status_code=400, detail="Not enough unreserved units remain for this serial number")

    inventory, product, batch = match
    stock_available = available_quantity(db, inventory)
    if stock_available < scan.quantity:
        raise HTTPException(status_code=400, detail=f"Only {stock_available} unreserved units remain in stock")

    inventory.quantity -= scan.quantity
    movement = InventoryMovement(
        inventory_id=inventory.inventory_id,
        product_id=inventory.product_id,
        batch_id=inventory.batch_id,
        warehouse_id=inventory.warehouse_id,
        movement_type="PICKED",
        event_key=event_key,
        quantity=scan.quantity,
        actor_id=current_user["user_id"],
        actor_name=current_user["username"],
        reason=f"Barcode scan {scan.scanned_code} reduced stock.",
    )
    db.add(movement)
    db.commit()
    return {
        "message": "Stock reduced",
        "scan_event_id": scan.scan_event_id,
        "movement_id": movement.movement_id,
        "product_name": product.name,
        "batch_number": batch.batch_number,
        "quantity_removed": scan.quantity,
        "remaining_quantity": inventory.quantity,
        "duplicate": False,
    }


@router.get("/expiring")
def get_expiring_inventory(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory"))
):
    process_expiry(db)
    days = max(1, min(days, 365))
    warehouse_id = current_user.get("warehouse_id")
    today = date.today()

    inventory = (
        db.query(Inventory, Batch, Product)
        .join(Batch, Inventory.batch_id == Batch.batch_id)
        .join(Product, Inventory.product_id == Product.product_id)
        .filter(
            Batch.expiry_date >= today,
            Batch.expiry_date <= today.fromordinal(
                today.toordinal() + days
            ),
            Inventory.warehouse_id == warehouse_id,
        )
        .order_by(Batch.expiry_date.asc())
        .all()
    )

    results = []

    for inventory_record, batch, product in inventory:
        days_remaining = (batch.expiry_date - today).days
        results.append({
            "inventory_id": inventory_record.inventory_id,
            "product_id": inventory_record.product_id,
            "product_name": product.name,
            "warehouse_id": inventory_record.warehouse_id,
            "batch_id": batch.batch_id,
            "batch_number": batch.batch_number,
            "quantity": inventory_record.quantity,
            "expiry_date": batch.expiry_date,
            "status": "URGENT" if days_remaining <= 1 else "EXPIRING SOON",
            "days_remaining": days_remaining,
            "estimated_value": inventory_record.quantity * product.price,
        })

    return {
        "days": days,
        "items": results
    }


@router.get("/expired")
def get_expired_inventory(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory")),
):
    process_expiry(db)
    rows = db.query(Inventory, Batch, Product).join(
        Batch, Inventory.batch_id == Batch.batch_id
    ).join(Product, Inventory.product_id == Product.product_id).filter(
        Inventory.warehouse_id == current_user.get("warehouse_id"),
        Batch.expiry_date <= date.today(),
        Inventory.expired_quantity > 0,
    ).order_by(Batch.expiry_date.desc()).all()
    return {"items": [
        {
            "inventory_id": inventory.inventory_id,
            "product_id": product.product_id,
            "product_name": product.name,
            "batch_id": batch.batch_id,
            "batch_number": batch.batch_number,
            "quantity": inventory.expired_quantity,
            "expiry_date": batch.expiry_date,
            "status": "EXPIRED",
            "estimated_value": inventory.expired_quantity * product.price,
        }
        for inventory, batch, product in rows
    ]}


@router.get("/history")
def get_inventory_history(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory")),
):
    movements = db.query(InventoryMovement).filter(
        InventoryMovement.warehouse_id == current_user.get("warehouse_id"),
    ).order_by(InventoryMovement.created_at.desc()).limit(200).all()
    return {"movements": movements}

@router.get("/")
def get_inventory(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_inventory"))):
    process_expiry(db)
    inventory = db.query(Inventory).filter(
        Inventory.warehouse_id == current_user.get("warehouse_id")
    ).all()

    return {"inventory": [
        {"inventory_id": row.inventory_id, "product_id": row.product_id, "warehouse_id": row.warehouse_id,
         "batch_id": row.batch_id, "quantity": row.quantity, "boxed_units": row.boxed_units,
         "units_per_box": row.units_per_box, "unit_price": row.unit_price,
         "box_unit_cost": row.box_unit_cost, "total_box_cost": row.total_box_cost,
         "expired_quantity": row.expired_quantity,
         "storage_zone": row.storage_zone, "location_code": row.location_code, "putaway_status": row.putaway_status,
         "batch_status": db.query(Batch.status).filter(Batch.batch_id == row.batch_id).scalar(),
         "batch_number": db.query(Batch.batch_number).filter(Batch.batch_id == row.batch_id).scalar(),
         "serial_number": db.query(Batch.serial_number).filter(Batch.batch_id == row.batch_id).scalar(),
         "expiry_date": db.query(Batch.expiry_date).filter(Batch.batch_id == row.batch_id).scalar(),
         "boxed_unit_ids": [box.box_code for box in db.query(BoxedUnit).filter(BoxedUnit.inventory_id == row.inventory_id).all()]}
        for row in inventory
    ]}

@router.get("/warehouse/{warehouse_id}")
def get_warehouse_inventory(
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory"))
):
    inventory = db.query(Inventory).filter(
        Inventory.warehouse_id == warehouse_id
    ).filter(Inventory.warehouse_id == current_user.get("warehouse_id")).all()

    return {
        "warehouse_id": warehouse_id,
        "inventory": inventory
    }

@router.get("/product/{product_id}")
def get_product_inventory(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory"))
):
    inventory = db.query(Inventory).filter(
        Inventory.product_id == product_id
    ).filter(Inventory.warehouse_id == current_user.get("warehouse_id")).all()

    return {
        "product_id": product_id,
        "inventory": inventory
    }

@router.get("/fefo/{product_id}")
def get_fefo_stock(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory"))
):
    inventory = (
        db.query(Inventory, Batch)
        .join(Batch, Inventory.batch_id == Batch.batch_id)
        .filter(
            Inventory.product_id == product_id,
            Inventory.warehouse_id == current_user.get("warehouse_id"),
            Inventory.quantity > 0,
            Inventory.putaway_status == "confirmed",
            Batch.status == "active",
            Batch.expiry_date > date.today()
        )
        .order_by(Batch.expiry_date.asc())
        .all()
    )

    return {
        "product_id": product_id,
        "batches": [
            {
                "inventory_id": inventory_record.inventory_id,
                "warehouse_id": inventory_record.warehouse_id,
                "batch_id": batch.batch_id,
                "batch_number": batch.batch_number,
                "quantity": inventory_record.quantity,
                "expiry_date": batch.expiry_date
            }
            for inventory_record, batch in inventory
        ]
    }