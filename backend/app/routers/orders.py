from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.order import SalesOrder
from app.models.order_item import SalesOrderItem
from app.models.product import Product
from app.schemas.order import SalesOrderCreate
from app.auth.dependencies import get_current_user, require_permission
from fastapi import APIRouter, Depends, HTTPException
from datetime import date, datetime
from app.services.order_status import OrderStatus
from app.models.inventory import Inventory
from app.models.boxed_unit import BoxedUnit
from app.models.order_pick_scan import OrderPickScan
from app.models.batch import Batch
from app.models.customer import Customer
from app.services.activity import log_activity
from app.services.notification import create_notification, notify_roles
from app.models.warehouse_request import WarehouseRequest
from app.models.inventory_movement import InventoryMovement
from app.models.counter_inventory import CounterInventory
from app.models.order_inventory_reservation import OrderInventoryReservation
from app.schemas.warehouse_request import WarehouseRequestCreate
from app.schemas.warehouse_workflow import OrderPickScanCreate
from app.services.order_reservations import available_quantity, release_order_reservations


router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)


def _fefo_plan(db: Session, product_id: int, warehouse_id: int, quantity: int, lock: bool = False) -> list[dict]:
    query = db.query(Inventory, Batch).join(
        Batch, Inventory.batch_id == Batch.batch_id
    ).filter(
        Inventory.product_id == product_id,
        Inventory.warehouse_id == warehouse_id,
        Inventory.quantity > 0,
        Inventory.putaway_status == "confirmed",
        Batch.status == "active",
        Batch.expiry_date > date.today(),
    ).order_by(Batch.expiry_date.asc())
    if lock:
        query = query.with_for_update()
    rows = query.all()
    if sum(row.quantity for row, _batch in rows) < quantity:
        return []
    remaining = quantity
    plan = []
    for inventory, batch in rows:
        picked = min(inventory.quantity, remaining)
        plan.append({"inventory_id": inventory.inventory_id, "batch_id": batch.batch_id, "batch_number": batch.batch_number, "quantity": picked, "expiry_date": batch.expiry_date})
        remaining -= picked
        if remaining == 0:
            break
    return plan


@router.get("/warehouse-requests")
def list_warehouse_requests(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_orders")),
):
    query = db.query(WarehouseRequest).filter(WarehouseRequest.warehouse_id == current_user.get("warehouse_id"))
    rows = query.order_by(WarehouseRequest.created_at.desc()).all()
    return {
        "requests": [
            {
                "request_id": item.request_id,
                "product_id": item.product_id,
                "product_name": db.query(Product.name).filter(Product.product_id == item.product_id).scalar(),
                "quantity": item.quantity,
                "status": item.status,
                "requested_by": item.requested_by,
                "created_at": item.created_at,
            }
            for item in rows
        ]
    }


@router.post("/warehouse-requests")
def request_warehouse_stock(
    request: WarehouseRequestCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("request_warehouse_stock")),
):
    if db.query(Product).filter(Product.product_id == request.product_id).first() is None:
        raise HTTPException(status_code=404, detail="Product not found")
    item = WarehouseRequest(product_id=request.product_id, quantity=request.quantity, warehouse_id=current_user.get("warehouse_id"), requested_by=current_user["user_id"])
    db.add(item)
    db.flush()
    notify_roles(db, {"warehouse_worker"}, "Warehouse stock request", f"Stock request #{item.request_id} needs action.", "warehouse_stock_request", current_user.get("warehouse_id"))
    db.commit()
    return {"message": "Stock request sent to warehouse", "request_id": item.request_id, "status": item.status}


@router.patch("/warehouse-requests/{request_id}/approve")
def approve_warehouse_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("process_stock_requests")),
):
    item = db.query(WarehouseRequest).filter(WarehouseRequest.request_id == request_id, WarehouseRequest.warehouse_id == current_user.get("warehouse_id"), WarehouseRequest.status == "pending").with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="Pending stock request not found")
    inventory_rows = db.query(Inventory).join(Batch, Inventory.batch_id == Batch.batch_id).filter(Inventory.product_id == item.product_id, Inventory.warehouse_id == item.warehouse_id, Inventory.quantity > 0, Inventory.putaway_status == "confirmed", Batch.status == "active", Batch.expiry_date > date.today()).order_by(Batch.expiry_date.asc()).with_for_update().all()
    if sum(available_quantity(db, row) for row in inventory_rows) < item.quantity:
        raise HTTPException(status_code=400, detail="Insufficient unexpired warehouse inventory")
    remaining = item.quantity
    product = db.query(Product).filter(Product.product_id == item.product_id).first()
    for inventory in inventory_rows:
        deduction = min(available_quantity(db, inventory), remaining)
        inventory.quantity -= deduction
        counter_inventory = db.query(CounterInventory).filter(
            CounterInventory.warehouse_id == item.warehouse_id,
            CounterInventory.product_id == item.product_id,
            CounterInventory.batch_id == inventory.batch_id,
        ).with_for_update().first()
        if counter_inventory is None:
            counter_inventory = CounterInventory(
                warehouse_id=item.warehouse_id,
                product_id=item.product_id,
                batch_id=inventory.batch_id,
                quantity=deduction,
                minimum_level=product.reorder_level if product else 0,
                unit_price=product.price if product else 0,
                last_replenished_at=datetime.utcnow(),
            )
            db.add(counter_inventory)
        else:
            counter_inventory.quantity += deduction
            counter_inventory.last_replenished_at = datetime.utcnow()
        db.add(InventoryMovement(
            inventory_id=inventory.inventory_id,
            product_id=inventory.product_id,
            batch_id=inventory.batch_id,
            warehouse_id=inventory.warehouse_id,
            movement_type="TRANSFER_TO_COUNTER",
            quantity=deduction,
            actor_id=current_user["user_id"],
            actor_name=current_user["username"],
            reason=f"Warehouse request #{item.request_id} transferred to counter using FEFO.",
        ))
        remaining -= deduction
        if remaining == 0:
            break
    item.status = "approved"
    item.approved_by = current_user["user_id"]
    item.approved_at = datetime.utcnow()
    create_notification(db, item.requested_by, "Stock request fulfilled", f"Request #{item.request_id} was transferred to counter inventory.", "warehouse_stock_approved")
    db.commit()
    return {"message": "Stock request approved", "request_id": request_id, "status": item.status}


@router.patch("/warehouse-requests/{request_id}/reject")
def reject_warehouse_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("process_stock_requests")),
):
    item = db.query(WarehouseRequest).filter(WarehouseRequest.request_id == request_id, WarehouseRequest.warehouse_id == current_user.get("warehouse_id"), WarehouseRequest.status == "pending").with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="Pending stock request not found")
    item.status = "rejected"
    item.approved_by = current_user["user_id"]
    item.approved_at = datetime.utcnow()
    create_notification(db, item.requested_by, "Stock request rejected", f"Request #{item.request_id} was rejected.", "warehouse_stock_rejected")
    db.commit()
    return {"message": "Stock request rejected", "request_id": request_id, "status": item.status}


@router.get("/")
def list_orders(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_orders"))
):
    query = db.query(SalesOrder).order_by(SalesOrder.created_at.desc())
    query = query.filter(SalesOrder.warehouse_id == current_user.get("warehouse_id"))

    orders = query.all()

    items_by_order: dict[int, list[dict]] = {}
    order_ids = [order.order_id for order in orders]
    if order_ids:
        rows = db.query(SalesOrderItem.order_id, SalesOrderItem.product_id, Product.name, SalesOrderItem.quantity).join(
            Product, SalesOrderItem.product_id == Product.product_id
        ).filter(SalesOrderItem.order_id.in_(order_ids)).all()
        for order_id, product_id, product_name, quantity in rows:
            items_by_order.setdefault(order_id, []).append({"product_id": product_id, "product_name": product_name, "quantity": quantity})

    picks_by_order: dict[int, dict[int, int]] = {}
    if order_ids:
        picked_rows = db.query(OrderPickScan.order_id, OrderPickScan.product_id, func.sum(OrderPickScan.quantity)).filter(
            OrderPickScan.order_id.in_(order_ids),
            OrderPickScan.is_valid == True,
        ).group_by(OrderPickScan.order_id, OrderPickScan.product_id).all()
        for order_id, product_id, quantity in picked_rows:
            picks_by_order.setdefault(order_id, {})[product_id] = int(quantity)

    return {
        "orders": [
            {
                "order_id": order.order_id,
                "customer_id": order.customer_id,
                "created_by": order.created_by,
                "status": order.status,
                "reservation_status": order.reservation_status,
                "created_at": order.created_at,
                "items": items_by_order.get(order.order_id, []),
                "pick_progress": picks_by_order.get(order.order_id, {}),
            }
            for order in orders
        ]
    }


@router.post("/")
def create_order(
    order: SalesOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("create_orders")
    )
):
    customer = db.query(Customer).filter(Customer.customer_id == order.customer_id).first() if order.customer_id else None
    if customer is None and order.customer_name:
        customer = Customer(name=order.customer_name.strip(), phone="Not provided")
        db.add(customer)
        db.flush()
    if customer is None:
        raise HTTPException(status_code=400, detail="Enter a customer name or select a valid customer")

    new_order = SalesOrder(
        customer_id=customer.customer_id,
        created_by=current_user["user_id"],
        warehouse_id=current_user.get("warehouse_id"),
        status="pending"
    )

    db.add(new_order)
    db.flush()
    notify_roles(
        db=db,
        roles={"manager"},
        title="New sales order",
        message=f"Sales order #{new_order.order_id} is waiting for approval.",
        notification_type="order_pending",
        warehouse_id=current_user.get("warehouse_id"),
    )
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="create_order",
    description=f"Created sales order #{new_order.order_id}"
)

    for item in order.items:
        product = db.query(Product).filter(
            Product.product_id == item.product_id
        ).first()

        if product is None:
            raise HTTPException(
                status_code=404,
                detail=f"Product {item.product_id} does not exist"
            )

        order_item = SalesOrderItem(
            order_id=new_order.order_id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=product.price
        )

        db.add(order_item)

    db.commit()
    db.refresh(new_order)

    return {
        "message": "Sales order created successfully",
        "order_id": new_order.order_id,
        "created_by": current_user["username"],
        "status": new_order.status
    }

@router.patch("/{order_id}/approve")
def approve_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("approve_sales_orders")
    )
):
    order = db.query(SalesOrder).filter(
        SalesOrder.order_id == order_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
    ).with_for_update().first()

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(
            status_code=400,
            detail="Only pending orders can be approved"
        )

    requested_quantities = {}
    for item in db.query(SalesOrderItem).filter(SalesOrderItem.order_id == order_id).all():
        requested_quantities[item.product_id] = requested_quantities.get(item.product_id, 0) + item.quantity
    for product_id, requested_quantity in sorted(requested_quantities.items()):
        available = db.query(Inventory).join(Batch, Inventory.batch_id == Batch.batch_id).filter(
            Inventory.product_id == product_id,
            Inventory.warehouse_id == current_user.get("warehouse_id"),
            Inventory.quantity > 0,
            Inventory.putaway_status == "confirmed",
            Batch.status == "active",
            Batch.expiry_date > date.today(),
        ).with_for_update().all()
        remaining = requested_quantity
        for row in available:
            reserved = min(available_quantity(db, row), remaining)
            if reserved:
                db.add(OrderInventoryReservation(
                    order_id=order.order_id,
                    inventory_id=row.inventory_id,
                    product_id=row.product_id,
                    batch_id=row.batch_id,
                    warehouse_id=row.warehouse_id,
                    quantity=reserved,
                ))
                remaining -= reserved
            if remaining == 0:
                break
        if remaining:
            raise HTTPException(status_code=400, detail=f"Insufficient unexpired inventory for product {product_id}")

    order.status = OrderStatus.APPROVED.value
    order.reservation_status = "reserved"
    create_notification(
        db=db,
        user_id=order.created_by,
        title="Order approved",
        message=f"Sales order #{order.order_id} was approved.",
        notification_type="order_approved",
    )
    notify_roles(
        db=db,
        roles={"warehouse_worker"},
        title="Order ready to dispatch",
        message=f"Sales order #{order.order_id} is approved and ready to dispatch.",
        notification_type="order_ready_to_dispatch",
        warehouse_id=order.warehouse_id,
    )
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="approve_order",
    description=f"Approved sales order #{order.order_id}"
)

    db.commit()
    db.refresh(order)

    return {
        "message": "Order approved successfully",
        "order_id": order.order_id,
        "status": order.status,
        "approved_by": current_user["username"]
    }

@router.patch("/{order_id}/reject")
def reject_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("approve_sales_orders")
    )
):
    order = db.query(SalesOrder).filter(
        SalesOrder.order_id == order_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
    ).with_for_update().first()

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(
            status_code=400,
            detail="Only pending orders can be rejected"
        )

    order.status = OrderStatus.REJECTED.value
    create_notification(
        db=db,
        user_id=order.created_by,
        title="Order rejected",
        message=f"Sales order #{order.order_id} was rejected.",
        notification_type="order_rejected",
    )
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="reject_order",
    description=f"Rejected sales order #{order.order_id}"
)

    db.commit()
    db.refresh(order)

    return {
        "message": "Order rejected successfully",
        "order_id": order.order_id,
        "status": order.status,
        "rejected_by": current_user["username"]
    }


@router.patch("/{order_id}/cancel")
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("approve_sales_orders")),
):
    order = db.query(SalesOrder).filter(
        SalesOrder.order_id == order_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
    ).with_for_update().first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status not in {OrderStatus.PENDING.value, OrderStatus.APPROVED.value}:
        raise HTTPException(status_code=400, detail="Only pending or approved orders can be cancelled")
    release_order_reservations(db, order.order_id)
    db.query(OrderPickScan).filter(OrderPickScan.order_id == order.order_id).update(
        {OrderPickScan.is_valid: False}, synchronize_session=False
    )
    order.status = OrderStatus.CANCELLED.value
    order.reservation_status = "released"
    create_notification(db, order.created_by, "Order cancelled", f"Sales order #{order.order_id} was cancelled.", "order_cancelled")
    log_activity(db, current_user["user_id"], current_user["username"], "cancel_order", f"Cancelled sales order #{order.order_id} and released its inventory reservations.")
    db.commit()
    return {"message": "Order cancelled and reservations released", "order_id": order_id, "status": order.status}


@router.get("/{order_id}")
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_orders"))
):
    order = db.query(SalesOrder).filter(
        SalesOrder.order_id == order_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
    ).first()

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    items = db.query(SalesOrderItem, Product.name).join(
        Product, SalesOrderItem.product_id == Product.product_id
    ).filter(
        SalesOrderItem.order_id == order_id
    ).all()

    return {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "created_by": order.created_by,
        "warehouse_id": order.warehouse_id,
        "status": order.status,
        "reservation_status": order.reservation_status,
        "created_at": order.created_at,
        "items": [
            {
                "product_id": item.product_id,
                "product_name": product_name,
                "quantity": item.quantity,
                "unit_price": item.unit_price
            }
            for item, product_name in items
        ],
        "fefo_allocations": [
            {
                "product_id": item.product_id,
                "product_name": product_name,
                "allocations": _fefo_plan(db, item.product_id, order.warehouse_id, item.quantity),
            }
            for item, product_name in items
        ] if order.status == OrderStatus.APPROVED.value else [],
        "pick_progress": {
            product_id: int(quantity)
            for product_id, quantity in db.query(OrderPickScan.product_id, func.sum(OrderPickScan.quantity)).filter(
                OrderPickScan.order_id == order_id,
                OrderPickScan.is_valid == True,
            ).group_by(OrderPickScan.product_id).all()
        },
    }


@router.post("/{order_id}/pick-scan")
def scan_order_pick(
    order_id: int,
    scan: OrderPickScanCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("pick_stock")),
):
    prior = db.query(OrderPickScan).filter(OrderPickScan.event_key == scan.event_key).first()
    if prior:
        if prior.order_id != order_id:
            raise HTTPException(status_code=409, detail="Scan event was already used for another order")
        if not prior.is_valid:
            raise HTTPException(status_code=409, detail="This pick was invalidated by a quality hold; scan the item again")
        return {"message": "Scan already recorded", "duplicate": True, "picked_quantity": prior.quantity}

    order = db.query(SalesOrder).filter(
        SalesOrder.order_id == order_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
        SalesOrder.status == OrderStatus.APPROVED.value,
    ).with_for_update().first()
    if order is None:
        raise HTTPException(status_code=404, detail="Approved order not found")

    match = db.query(Inventory, Batch, BoxedUnit).join(
        Batch, Inventory.batch_id == Batch.batch_id
    ).join(
        BoxedUnit, BoxedUnit.inventory_id == Inventory.inventory_id
    ).join(
        OrderInventoryReservation, OrderInventoryReservation.inventory_id == Inventory.inventory_id
    ).filter(
        OrderInventoryReservation.order_id == order_id,
        OrderInventoryReservation.status == "reserved",
        Inventory.warehouse_id == order.warehouse_id,
        Inventory.putaway_status == "confirmed",
        Inventory.quantity > 0,
        Batch.status == "active",
        Batch.expiry_date > date.today(),
        (BoxedUnit.scanned_code == scan.scanned_code) | (BoxedUnit.box_code == scan.scanned_code),
    ).order_by(Batch.expiry_date.asc(), Inventory.inventory_id.asc()).with_for_update().first()
    if match is None:
        match = db.query(Inventory, Batch).join(
            Batch, Inventory.batch_id == Batch.batch_id
        ).join(
            OrderInventoryReservation, OrderInventoryReservation.inventory_id == Inventory.inventory_id
        ).filter(
            OrderInventoryReservation.order_id == order_id,
            OrderInventoryReservation.status == "reserved",
            Inventory.warehouse_id == order.warehouse_id,
            Inventory.putaway_status == "confirmed",
            Inventory.quantity > 0,
            Batch.status == "active",
            Batch.expiry_date > date.today(),
            Batch.batch_number == scan.scanned_code,
        ).order_by(Batch.expiry_date.asc(), Inventory.inventory_id.asc()).with_for_update().first()
        if match is not None:
            inventory, batch = match
            boxed_unit = None
        else:
            inventory = batch = boxed_unit = None
    else:
        inventory, batch, boxed_unit = match
    if match is None:
        raise HTTPException(status_code=404, detail="Barcode or batch is not available for picking in this warehouse")

    requested_quantity = db.query(func.coalesce(func.sum(SalesOrderItem.quantity), 0)).filter(
        SalesOrderItem.order_id == order_id,
        SalesOrderItem.product_id == inventory.product_id,
    ).scalar()
    if not requested_quantity:
        raise HTTPException(status_code=400, detail="Scanned product is not part of this order")
    already_picked = db.query(func.coalesce(func.sum(OrderPickScan.quantity), 0)).filter(
        OrderPickScan.order_id == order_id,
        OrderPickScan.product_id == inventory.product_id,
        OrderPickScan.is_valid == True,
    ).scalar()
    if already_picked + scan.quantity > requested_quantity:
        raise HTTPException(status_code=400, detail="Scan exceeds the quantity requested for this product")

    candidates = db.query(Inventory, Batch, OrderInventoryReservation).join(Batch, Inventory.batch_id == Batch.batch_id).join(
        OrderInventoryReservation, OrderInventoryReservation.inventory_id == Inventory.inventory_id
    ).filter(
        OrderInventoryReservation.order_id == order_id,
        OrderInventoryReservation.status == "reserved",
        Inventory.product_id == inventory.product_id,
        Inventory.warehouse_id == order.warehouse_id,
        Inventory.quantity > 0,
        Inventory.putaway_status == "confirmed",
        Batch.status == "active",
        Batch.expiry_date > date.today(),
    ).order_by(Batch.expiry_date.asc(), Inventory.inventory_id.asc()).with_for_update().all()
    expected_inventory = None
    for candidate, _candidate_batch, reservation in candidates:
        already_picked_from_inventory = db.query(func.coalesce(func.sum(OrderPickScan.quantity), 0)).filter(
            OrderPickScan.order_id == order_id,
            OrderPickScan.inventory_id == candidate.inventory_id,
            OrderPickScan.is_valid == True,
        ).scalar()
        if reservation.quantity - already_picked_from_inventory > 0:
            expected_inventory = candidate
            break
    if expected_inventory is None or expected_inventory.inventory_id != inventory.inventory_id:
        raise HTTPException(status_code=409, detail="Pick the available batch with the earliest expiry date first")
    if boxed_unit is not None:
        box_reserved = db.query(func.coalesce(func.sum(OrderPickScan.quantity), 0)).join(
            SalesOrder, OrderPickScan.order_id == SalesOrder.order_id
        ).filter(
            OrderPickScan.boxed_unit_id == boxed_unit.boxed_unit_id,
            OrderPickScan.is_valid == True,
            SalesOrder.status == OrderStatus.APPROVED.value,
        ).scalar()
        if boxed_unit.remaining_units - box_reserved < scan.quantity:
            raise HTTPException(status_code=400, detail="Barcode has insufficient unreserved units")

    db.add(OrderPickScan(
        event_key=scan.event_key,
        order_id=order_id,
        inventory_id=inventory.inventory_id,
        product_id=inventory.product_id,
        batch_id=batch.batch_id,
        boxed_unit_id=boxed_unit.boxed_unit_id if boxed_unit else None,
        scanned_code=scan.scanned_code,
        quantity=scan.quantity,
        actor_name=current_user.get("username"),
        actor_id=current_user["user_id"],
    ))
    db.commit()
    picked_total = already_picked + scan.quantity
    return {
        "message": "Pick scan verified",
        "duplicate": False,
        "product_id": inventory.product_id,
        "batch_number": batch.batch_number,
        "expiry_date": batch.expiry_date,
        "location_code": inventory.location_code,
        "picked_quantity": picked_total,
        "requested_quantity": int(requested_quantity),
    }

@router.patch("/{order_id}/fulfill")
def fulfill_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("fulfill_orders")
    )
):
    order = db.query(SalesOrder).filter(
        SalesOrder.order_id == order_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
    ).with_for_update().first()

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    if order.status != OrderStatus.APPROVED.value:
        raise HTTPException(
            status_code=400,
            detail="Only approved orders can be fulfilled"
        )

    if order.reservation_status != "reserved":
        raise HTTPException(status_code=409, detail="Order stock is not fully reserved. Cancel or replace this order before dispatch.")

    items = db.query(SalesOrderItem).filter(
        SalesOrderItem.order_id == order_id
    ).all()

    if not items:
        raise HTTPException(
            status_code=400,
            detail="Order contains no items"
        )

    requested_by_product: dict[int, int] = {}
    for item in items:
        requested_by_product[item.product_id] = requested_by_product.get(item.product_id, 0) + item.quantity
    picked_by_product = {
        product_id: int(quantity)
        for product_id, quantity in db.query(OrderPickScan.product_id, func.sum(OrderPickScan.quantity)).filter(
            OrderPickScan.order_id == order_id,
            OrderPickScan.is_valid == True,
        ).group_by(OrderPickScan.product_id).all()
    }
    if any(picked_by_product.get(product_id, 0) < quantity for product_id, quantity in requested_by_product.items()):
        raise HTTPException(status_code=400, detail="Scan and verify every item before dispatch")

    pick_scans = db.query(OrderPickScan).filter(OrderPickScan.order_id == order_id, OrderPickScan.is_valid == True).with_for_update().all()
    reservations = db.query(OrderInventoryReservation).filter(
        OrderInventoryReservation.order_id == order_id,
        OrderInventoryReservation.status == "reserved",
    ).with_for_update().all()
    reserved_by_inventory = {item.inventory_id: item.quantity for item in reservations}
    picked_by_inventory = {}
    for pick in pick_scans:
        picked_by_inventory[pick.inventory_id] = picked_by_inventory.get(pick.inventory_id, 0) + pick.quantity
    if any(picked > reserved_by_inventory.get(inventory_id, 0) for inventory_id, picked in picked_by_inventory.items()):
        raise HTTPException(status_code=409, detail="Picked quantities exceed this order's inventory reservations")
    if any(picked_by_inventory.get(item.inventory_id, 0) != item.quantity for item in reservations):
        raise HTTPException(status_code=409, detail="Reserved stock was not fully picked; cancel or replace the order")
    for pick in pick_scans:
        inventory = db.query(Inventory).filter(Inventory.inventory_id == pick.inventory_id).with_for_update().first()
        batch = db.query(Batch).filter(Batch.batch_id == pick.batch_id).with_for_update().first()
        if inventory is None or batch is None or inventory.quantity < pick.quantity or inventory.putaway_status != "confirmed" or batch.status != "active" or batch.expiry_date <= date.today():
            raise HTTPException(status_code=409, detail="Picked inventory changed before dispatch")
        inventory.quantity -= pick.quantity
        if pick.boxed_unit_id is not None:
            boxed_unit = db.query(BoxedUnit).filter(BoxedUnit.boxed_unit_id == pick.boxed_unit_id).with_for_update().first()
            if boxed_unit is None or boxed_unit.remaining_units < pick.quantity:
                raise HTTPException(status_code=409, detail="Scanned box quantity changed before dispatch")
            boxed_unit.remaining_units -= pick.quantity
        db.add(InventoryMovement(
            inventory_id=inventory.inventory_id,
            product_id=inventory.product_id,
            batch_id=inventory.batch_id,
            warehouse_id=inventory.warehouse_id,
            movement_type="SOLD",
            event_key=f"order-pick:{pick.event_key}",
            quantity=pick.quantity,
            actor_id=current_user["user_id"],
            actor_name=current_user["username"],
            reason=f"Sales order #{order.order_id} dispatched after verified FEFO pick.",
        ))

    for reservation in reservations:
        reservation.status = "consumed"

    order.status = OrderStatus.FULFILLED.value
    create_notification(
        db=db,
        user_id=order.created_by,
        title="Order fulfilled",
        message=f"Sales order #{order.order_id} was fulfilled.",
        notification_type="order_fulfilled",
    )
    log_activity(db, current_user["user_id"], current_user["username"], "fulfill_order", f"Fulfilled sales order #{order.order_id} using FEFO allocation.")

    db.commit()
    db.refresh(order)

    return {
        "message": "Order fulfilled successfully",
        "order_id": order.order_id,
        "status": order.status,
        "fulfilled_by": current_user["username"],
        "fefo_allocations": [
            {"inventory_id": pick.inventory_id, "batch_id": pick.batch_id, "quantity": pick.quantity, "batch_number": db.query(Batch.batch_number).filter(Batch.batch_id == pick.batch_id).scalar(), "expiry_date": db.query(Batch.expiry_date).filter(Batch.batch_id == pick.batch_id).scalar()}
            for pick in pick_scans
        ]
    }


@router.patch("/{order_id}/confirm-receipt")
def confirm_order_receipt(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("confirm_order_receipt")),
):
    order = db.query(SalesOrder).filter(
        SalesOrder.order_id == order_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
        SalesOrder.created_by == current_user["user_id"],
    ).with_for_update().first()
    if order is None:
        raise HTTPException(status_code=404, detail="Your order was not found")
    if order.status != OrderStatus.FULFILLED.value:
        raise HTTPException(status_code=400, detail="Only fulfilled orders can be confirmed as received")
    order.status = "confirmed"
    order.confirmed_by = current_user["user_id"]
    order.confirmed_at = datetime.utcnow()
    create_notification(db, current_user["user_id"], "Order receipt confirmed", f"Sales order #{order.order_id} was marked received.", "order_received")
    db.commit()
    return {"message": "Order receipt confirmed", "order_id": order_id, "status": order.status}