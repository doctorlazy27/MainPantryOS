from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.batch import Batch
from app.models.inventory import Inventory
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.user import User
from app.models.counter_inventory import CounterInventory
from app.services.activity import log_activity
from app.services.notification import create_notification_once
from app.services.order_reservations import release_batch_reservations


def process_expiry(db: Session, today: date | None = None) -> dict[str, int]:
    if db.bind and db.bind.dialect.name == "postgresql":
        locked = db.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": 774321}).scalar()
        if not locked:
            return {"expired_batches": 0, "expired_units": 0, "warnings": 0, "skipped": 1}
    current_day = today or date.today()
    expired_count = 0
    expired_units = 0
    warnings = 0

    rows = db.query(Inventory, Batch, Product).join(
        Batch, Inventory.batch_id == Batch.batch_id
    ).join(Product, Inventory.product_id == Product.product_id).filter(
        Batch.expiry_date <= current_day,
        Inventory.quantity > 0,
    ).with_for_update().all()

    for inventory, batch, product in rows:
        quantity = inventory.quantity
        inventory.quantity = 0
        inventory.expired_quantity = (inventory.expired_quantity or 0) + quantity
        batch.status = "expired"
        batch.expired_at = batch.expired_at or datetime.utcnow()
        release_batch_reservations(db, batch.batch_id, inventory.warehouse_id)
        existing_movement = db.query(InventoryMovement).filter(
            InventoryMovement.inventory_id == inventory.inventory_id,
            InventoryMovement.movement_type == "EXPIRED",
        ).first()
        if existing_movement:
            continue
        db.add(InventoryMovement(
            inventory_id=inventory.inventory_id,
            product_id=inventory.product_id,
            batch_id=inventory.batch_id,
            warehouse_id=inventory.warehouse_id,
            movement_type="EXPIRED",
            event_key=f"expired:{inventory.inventory_id}",
            quantity=quantity,
            actor_name="SYSTEM",
            reason="Batch expiry date reached.",
        ))
        log_activity(db, None, "SYSTEM", "expire_inventory", f"Expired {quantity} units of {product.name}, batch {batch.batch_number}.")
        _notify_expired(db, inventory, product, batch, quantity)
        expired_count += 1
        expired_units += quantity

    counter_rows = db.query(CounterInventory, Batch, Product).join(
        Batch, CounterInventory.batch_id == Batch.batch_id
    ).join(Product, CounterInventory.product_id == Product.product_id).filter(
        Batch.expiry_date <= current_day,
        CounterInventory.quantity > 0,
    ).with_for_update().all()
    for counter, batch, product in counter_rows:
        quantity = counter.quantity
        counter.quantity = 0
        existing_movement = db.query(InventoryMovement).filter(
            InventoryMovement.inventory_id == db.query(Inventory.inventory_id).filter(
                Inventory.product_id == counter.product_id,
                Inventory.batch_id == counter.batch_id,
                Inventory.warehouse_id == counter.warehouse_id,
            ).scalar_subquery(),
            InventoryMovement.movement_type == "COUNTER_EXPIRED",
            InventoryMovement.batch_id == counter.batch_id,
        ).first()
        if existing_movement:
            continue
        source_inventory_id = db.query(Inventory.inventory_id).filter(
            Inventory.product_id == counter.product_id,
            Inventory.batch_id == counter.batch_id,
            Inventory.warehouse_id == counter.warehouse_id,
        ).scalar()
        if source_inventory_id:
            db.add(InventoryMovement(
                inventory_id=source_inventory_id,
                product_id=counter.product_id,
                batch_id=counter.batch_id,
                warehouse_id=counter.warehouse_id,
                movement_type="COUNTER_EXPIRED",
                event_key=f"counter_expired:{counter.counter_inventory_id}",
                quantity=quantity,
                actor_name="SYSTEM",
                reason="Counter batch expiry date reached.",
            ))
        log_activity(db, None, "SYSTEM", "expire_counter_inventory", f"Expired {quantity} counter units of {product.name}, batch {batch.batch_number}.")
        users = db.query(User).filter(User.role.in_({"warehouse_worker", "manager"}), User.warehouse_id == counter.warehouse_id).all()
        for user in users:
            create_notification_once(db, user.user_id, "Counter batch expired", f"{product.name} batch {batch.batch_number} expired at the counter. {quantity} units were removed from saleable stock.", "counter_expired", f"counter_expired:{counter.counter_inventory_id}")
        expired_count += 1
        expired_units += quantity

    warning_rows = db.query(Inventory, Batch, Product).join(
        Batch, Inventory.batch_id == Batch.batch_id
    ).join(Product, Inventory.product_id == Product.product_id).filter(
        Batch.expiry_date > current_day,
        Inventory.quantity > 0,
        Batch.expiry_date <= current_day + timedelta(days=7),
    ).all()
    for inventory, batch, product in warning_rows:
        days = (batch.expiry_date - current_day).days
        if days in {7, 3, 1}:
            _notify_warning(db, inventory, product, batch, days)
            warnings += 1

    counter_warning_rows = db.query(CounterInventory, Batch, Product).join(Batch, CounterInventory.batch_id == Batch.batch_id).join(Product, CounterInventory.product_id == Product.product_id).filter(Batch.expiry_date > current_day, CounterInventory.quantity > 0, Batch.expiry_date <= current_day + timedelta(days=7)).all()
    for counter, batch, product in counter_warning_rows:
        days = (batch.expiry_date - current_day).days
        if days in {7, 3, 1}:
            users = db.query(User).filter(User.role.in_({"warehouse_worker", "manager"}), User.warehouse_id == counter.warehouse_id).all()
            for user in users:
                create_notification_once(db, user.user_id, "Counter expiry warning", f"Counter {product.name} batch {batch.batch_number} expires in {days} day(s). {counter.quantity} units remain.", "counter_expiry_warning", f"counter_expiry:{counter.counter_inventory_id}:{days}")
            warnings += 1

    db.commit()
    return {"expired_batches": expired_count, "expired_units": expired_units, "warnings": warnings}


def _notify_expired(db: Session, inventory: Inventory, product: Product, batch: Batch, quantity: int) -> None:
    message = f"{product.name} batch {batch.batch_number} at warehouse {inventory.warehouse_id} has expired. {quantity} units were removed from available inventory."
    users = db.query(User).filter(
        User.role.in_({"warehouse_worker", "manager"}),
        User.warehouse_id == inventory.warehouse_id,
    ).all()
    for user in users:
        create_notification_once(db, user.user_id, "Inventory batch expired", message, "inventory_expired", f"expired:{inventory.inventory_id}")


def _notify_warning(db: Session, inventory: Inventory, product: Product, batch: Batch, days: int) -> None:
    if days == 7:
        message = f"{product.name} batch {batch.batch_number} at warehouse {inventory.warehouse_id} expires in 7 days. {inventory.quantity} units remain."
    elif days == 3:
        message = f"{product.name} batch {batch.batch_number} at warehouse {inventory.warehouse_id} expires in 3 days. {inventory.quantity} units remain. Prioritize this batch."
    else:
        message = f"URGENT: {product.name} batch {batch.batch_number} at warehouse {inventory.warehouse_id} expires tomorrow. {inventory.quantity} units remain."
    users = db.query(User).filter(
        User.role.in_({"warehouse_worker", "manager"}),
        User.warehouse_id == inventory.warehouse_id,
    ).all()
    for user in users:
        create_notification_once(db, user.user_id, "Expiry warning", message, "inventory_expiry_warning", f"expiry:{inventory.inventory_id}:{days}")
