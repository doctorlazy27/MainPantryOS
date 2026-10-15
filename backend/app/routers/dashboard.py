from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.database import get_db
from app.models.batch import Batch
from app.models.inventory import Inventory
from app.models.notification import Notification
from app.models.message import Message
from app.models.order import SalesOrder
from app.models.order_item import SalesOrderItem
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.inventory_addition_request import InventoryAdditionRequest
from app.services.expiry import process_expiry
from app.services.intelligence import calculate_inventory_intelligence


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


@router.get("/")
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("view_activity")
    )
):
    process_expiry(db)
    warehouse_id = current_user.get("warehouse_id")
    total_products = db.query(Product).filter(Product.warehouse_id == warehouse_id).count()
    total_inventory_records = db.query(Inventory).filter(Inventory.warehouse_id == warehouse_id).count()

    pending_sales_orders = db.query(SalesOrder).filter(
        SalesOrder.status == "pending",
        SalesOrder.warehouse_id == warehouse_id,
    ).count()

    approved_sales_orders = db.query(SalesOrder).filter(
        SalesOrder.status == "approved",
        SalesOrder.warehouse_id == warehouse_id,
    ).count()

    pending_purchase_orders = db.query(InventoryAdditionRequest).filter(
        InventoryAdditionRequest.status.in_(["pending", "approved"]),
        InventoryAdditionRequest.warehouse_id == warehouse_id,
    ).count()

    unread_notifications = db.query(Notification).filter(
        Notification.user_id == current_user["user_id"],
        Notification.is_read == False
    ).count()
    unread_notifications += db.query(Message).filter(
        Message.recipient_id == current_user["user_id"],
        Message.is_read == False,
    ).count()

    # Calculate products that are at or below their reorder level.
    low_stock_products = []

    products = db.query(Product).filter(Product.warehouse_id == warehouse_id).all()

    for product in products:
        inventory_rows = db.query(Inventory).filter(
            Inventory.product_id == product.product_id,
            Inventory.warehouse_id == warehouse_id,
        ).all()

        total_quantity = sum(
            row.quantity for row in inventory_rows
        )

        if total_quantity <= product.reorder_level:
            low_stock_products.append({
                "product_id": product.product_id,
                "name": product.name,
                "current_quantity": total_quantity,
                "reorder_level": product.reorder_level,
                "unit": product.unit
            })

    # Find batches expiring within the next 7 days.
    today = date.today()
    expiry_limit = today + timedelta(days=7)

    expiring_batches = (
        db.query(Inventory, Batch, Product)
        .join(Batch, Inventory.batch_id == Batch.batch_id)
        .join(Product, Inventory.product_id == Product.product_id)
        .filter(
            Batch.expiry_date >= today,
            Batch.expiry_date <= expiry_limit,
            Inventory.quantity > 0
            ,Inventory.warehouse_id == warehouse_id
        )
        .order_by(Batch.expiry_date.asc())
        .all()
    )

    expiring_items = []

    for inventory, batch, product in expiring_batches:
        expiring_items.append({
            "product_id": product.product_id,
            "product_name": product.name,
            "warehouse_id": inventory.warehouse_id,
            "batch_id": batch.batch_id,
            "batch_number": batch.batch_number,
            "quantity": inventory.quantity,
            "expiry_date": batch.expiry_date
        })

    intelligence = calculate_inventory_intelligence(db, warehouse_id, today)

    return {
        "total_products": total_products,
        "total_inventory_records": total_inventory_records,
        "pending_sales_orders": pending_sales_orders,
        "approved_sales_orders": approved_sales_orders,
        "pending_purchase_orders": pending_purchase_orders,
        "unread_notifications": unread_notifications,
        "low_stock_products": low_stock_products,
        "expiring_batches": expiring_items
        ,"inventory_intelligence": intelligence
    }