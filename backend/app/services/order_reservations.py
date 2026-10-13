from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.order_inventory_reservation import OrderInventoryReservation
from app.models.order import SalesOrder


def reserved_quantity(db: Session, inventory_id: int) -> int:
    quantity = db.query(func.coalesce(func.sum(OrderInventoryReservation.quantity), 0)).filter(
        OrderInventoryReservation.inventory_id == inventory_id,
        OrderInventoryReservation.status == "reserved",
    ).scalar()
    return int(quantity or 0)


def available_quantity(db: Session, inventory: Inventory) -> int:
    return max(inventory.quantity - reserved_quantity(db, inventory.inventory_id), 0)


def release_order_reservations(db: Session, order_id: int) -> None:
    db.query(OrderInventoryReservation).filter(
        OrderInventoryReservation.order_id == order_id,
        OrderInventoryReservation.status == "reserved",
    ).update({OrderInventoryReservation.status: "released"}, synchronize_session=False)


def release_batch_reservations(db: Session, batch_id: int, warehouse_id: int) -> None:
    order_ids = [order_id for (order_id,) in db.query(OrderInventoryReservation.order_id).filter(
        OrderInventoryReservation.batch_id == batch_id,
        OrderInventoryReservation.warehouse_id == warehouse_id,
        OrderInventoryReservation.status == "reserved",
    ).distinct().all()]
    if not order_ids:
        return
    db.query(OrderInventoryReservation).filter(
        OrderInventoryReservation.batch_id == batch_id,
        OrderInventoryReservation.warehouse_id == warehouse_id,
        OrderInventoryReservation.status == "reserved",
    ).update({OrderInventoryReservation.status: "released"}, synchronize_session=False)
    db.query(SalesOrder).filter(
        SalesOrder.order_id.in_(order_ids),
        SalesOrder.status == "approved",
    ).update({SalesOrder.reservation_status: "short"}, synchronize_session=False)