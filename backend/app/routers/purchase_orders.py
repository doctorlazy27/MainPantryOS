from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.database import get_db
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.schemas.purchase_order import PurchaseOrderCreate
from app.auth.dependencies import require_permission
from app.models.batch import Batch
from app.models.inventory import Inventory
from app.models.inventory_movement import InventoryMovement
from app.models.temperature_log import TemperatureLog
from app.services.boxed_units import create_boxed_units
from app.services.cold_chain import temperature_is_safe, temperature_range
from app.models.warehouse import Warehouse
from app.models.supplier import Supplier
from app.schemas.receiving import ReceivePurchaseOrder
from app.services.ocr_provider import TextractNotConfigured, textract_provider_from_environment
from app.services.activity import log_activity
from app.services.notification import create_notification


router = APIRouter(
    prefix="/purchase-orders",
    tags=["Purchase Orders"]
)


@router.post("/{purchase_order_id}/parse-document")
async def parse_delivery_document(
    purchase_order_id: int,
    document: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("receive_purchase_orders")),
):
    purchase_order = db.query(PurchaseOrder).filter(
        PurchaseOrder.purchase_order_id == purchase_order_id,
        PurchaseOrder.warehouse_id == current_user.get("warehouse_id"),
        PurchaseOrder.status == "pending",
    ).first()
    if purchase_order is None:
        raise HTTPException(status_code=404, detail="Pending purchase order not found")
    if document.content_type not in {"application/pdf", "image/jpeg", "image/png", "image/tiff"}:
        raise HTTPException(status_code=415, detail="Upload a PDF, JPEG, PNG, or TIFF delivery document")
    contents = await document.read(5 * 1024 * 1024 + 1)
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Textract synchronous document uploads are limited to 5 MB")
    try:
        fields = textract_provider_from_environment().extract(contents)
    except TextractNotConfigured as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"purchase_order_id": purchase_order_id, "extracted": fields}

@router.get("/")
def list_purchase_orders(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory")),
):
    rows = db.query(PurchaseOrder, Supplier).join(
        Supplier, PurchaseOrder.supplier_id == Supplier.supplier_id
    ).filter(
        PurchaseOrder.warehouse_id == current_user.get("warehouse_id")
    ).order_by(PurchaseOrder.created_at.desc()).all()
    return {
        "purchase_orders": [
            {
                "purchase_order_id": order.purchase_order_id,
                "supplier_name": supplier.name,
                "warehouse_id": order.warehouse_id,
                "status": order.status,
                "created_at": order.created_at,
                "items": [
                    {
                        "product_id": item.product_id,
                        "product_name": db.query(Product.name).filter(Product.product_id == item.product_id).scalar(),
                        "quantity": item.quantity,
                    }
                    for item in db.query(PurchaseOrderItem).filter(PurchaseOrderItem.purchase_order_id == order.purchase_order_id).all()
                ],
            }
            for order, supplier in rows
        ]
    }

@router.patch("/{purchase_order_id}/receive")
def receive_purchase_order(
    purchase_order_id: int,
    receiving: ReceivePurchaseOrder,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("receive_purchase_orders")
    )
):
    purchase_order = db.query(PurchaseOrder).filter(
        PurchaseOrder.purchase_order_id == purchase_order_id,
        PurchaseOrder.warehouse_id == current_user.get("warehouse_id"),
    ).with_for_update().first()

    if purchase_order is None:
        raise HTTPException(
            status_code=404,
            detail="Purchase order not found"
        )

    if purchase_order.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Only pending purchase orders can be received"
        )

    if db.query(Warehouse).filter(Warehouse.warehouse_id == receiving.warehouse_id).first() is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    if receiving.warehouse_id != current_user.get("warehouse_id"):
        raise HTTPException(status_code=403, detail="You can only receive stock into your assigned warehouse")

    resolved_items = []
    for item in receiving.items:
        product = db.query(Product).filter(Product.product_id == item.product_id).first() if item.product_id else None
        if product is None and item.product_name:
            product = db.query(Product).filter(Product.name.ilike(item.product_name.strip())).first()
        if product is None:
            raise HTTPException(status_code=404, detail=f"Product '{item.product_name or item.product_id}' does not exist")
        resolved_items.append((item, product))

    purchase_items = db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.purchase_order_id == purchase_order_id
    ).all()
    ordered = {}
    for item in purchase_items:
        ordered[item.product_id] = ordered.get(item.product_id, 0) + item.quantity
    received = {}
    for item, product in resolved_items:
        received[product.product_id] = received.get(product.product_id, 0) + item.quantity

    if set(received) != set(ordered):
        raise HTTPException(status_code=400, detail="Received products must match the purchase order")
    if received != ordered:
        raise HTTPException(status_code=400, detail="Received quantities must match the purchase order")

    batch_numbers = [item.batch_number.strip() for item, _product in resolved_items]
    if any(not batch_number for batch_number in batch_numbers):
        raise HTTPException(status_code=400, detail="Every received line needs a batch number")
    if len({batch_number.casefold() for batch_number in batch_numbers}) != len(batch_numbers):
        raise HTTPException(status_code=409, detail="Each received lot needs a unique batch number")
    existing_batch = db.query(Batch.batch_number).filter(Batch.batch_number.in_(batch_numbers)).first()
    if existing_batch:
        raise HTTPException(status_code=409, detail=f"Batch number {existing_batch[0]} already exists")

    for (item, product), batch_number in zip(resolved_items, batch_numbers):
        if item.expiry_date <= item.manufacturing_date:
            raise HTTPException(status_code=400, detail="Expiry date must be after manufacturing date")
        if item.expiry_date <= date.today():
            raise HTTPException(status_code=400, detail="Cannot receive an already expired batch")

        temp_range = temperature_range(item.storage_zone)
        passed_qc = temperature_is_safe(item.storage_zone, item.temperature_c)
        batch = Batch(
            product_id=product.product_id,
            batch_number=batch_number,
            manufacturing_date=item.manufacturing_date,
            expiry_date=item.expiry_date,
            status="active" if passed_qc else "quarantined",
        )

        db.add(batch)
        try:
            db.flush()
        except IntegrityError as error:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"Batch number {batch_number} already exists") from error

        inventory = Inventory(
            product_id=product.product_id,
            warehouse_id=receiving.warehouse_id,
            batch_id=batch.batch_id,
            quantity=item.quantity,
            boxed_units=item.boxed_units,
            units_per_box=item.units_per_box,
            unit_price=item.unit_price,
            box_unit_cost=item.box_unit_cost or item.unit_price * item.units_per_box,
            total_box_cost=item.boxed_units * (item.box_unit_cost or item.unit_price * item.units_per_box),
            storage_zone=item.storage_zone,
            location_code="STAGING" if passed_qc else "QUARANTINE",
            putaway_status="pending" if passed_qc else "hold",
        )

        db.add(inventory)
        db.flush()
        create_boxed_units(db, inventory.inventory_id, item.boxed_units, item.units_per_box, item.unit_price, item.scanned_codes)
        db.add(TemperatureLog(
            batch_id=batch.batch_id,
            inventory_id=inventory.inventory_id,
            warehouse_id=receiving.warehouse_id,
            recorded_by=current_user["user_id"],
            stage="receiving",
            storage_zone=item.storage_zone,
            temperature_c=item.temperature_c,
            minimum_c=temp_range.minimum_c,
            maximum_c=temp_range.maximum_c,
            within_range=passed_qc,
        ))
        db.add(InventoryMovement(
            inventory_id=inventory.inventory_id,
            product_id=inventory.product_id,
            batch_id=inventory.batch_id,
            warehouse_id=inventory.warehouse_id,
            movement_type="RECEIVED",
            quantity=inventory.quantity,
            actor_id=current_user["user_id"],
            actor_name=current_user["username"],
            reason=f"Purchase order #{purchase_order_id} received.",
        ))

    purchase_order.status = "received"

    db.commit()
    db.refresh(purchase_order)

    return {
        "message": "Purchase order received successfully",
        "purchase_order_id": purchase_order.purchase_order_id,
        "warehouse_id": receiving.warehouse_id,
        "received_by": current_user["username"],
        "status": purchase_order.status
        ,"quarantined_batches": [
            item.batch_number for item in receiving.items
            if not temperature_is_safe(item.storage_zone, item.temperature_c)
        ]
    }





@router.post("/")
def create_purchase_order(
    purchase_order: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("create_purchase_orders")
    )
):
    supplier = db.query(Supplier).filter(Supplier.supplier_id == purchase_order.supplier_id).first() if purchase_order.supplier_id else None
    if supplier is None and purchase_order.supplier_name:
        supplier = Supplier(name=purchase_order.supplier_name.strip(), phone="Not provided")
        db.add(supplier)
        db.flush()
    if supplier is None:
        raise HTTPException(status_code=400, detail="Enter a supplier name or select a valid supplier")

    new_order = PurchaseOrder(
        supplier_id=supplier.supplier_id,
        created_by=current_user["user_id"],
        warehouse_id=current_user.get("warehouse_id"),
        status="pending"
    )

    db.add(new_order)
    db.flush()

    for item in purchase_order.items:
        product = db.query(Product).filter(Product.product_id == item.product_id).first() if item.product_id else None
        if product is None and item.product_name:
            product = db.query(Product).filter(Product.name.ilike(item.product_name.strip())).first()
        if product is None and item.product_name:
            product = Product(name=item.product_name.strip(), category="General", quantity=0, unit="units", price=0, reorder_level=0)
            db.add(product)
            db.flush()

        if product is None:
            raise HTTPException(
                status_code=404,
                detail=f"Product {item.product_id} does not exist"
            )

        order_item = PurchaseOrderItem(
            purchase_order_id=new_order.purchase_order_id,
            product_id=product.product_id,
            quantity=item.quantity,
            unit_price=product.price
        )

        db.add(order_item)

    db.commit()
    db.refresh(new_order)

    return {
        "message": "Purchase order created successfully",
        "purchase_order_id": new_order.purchase_order_id,
        "created_by": current_user["username"],
        "status": new_order.status
    }


@router.patch("/{purchase_order_id}/cancel")
def cancel_purchase_order(
    purchase_order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("create_purchase_orders")),
):
    purchase_order = db.query(PurchaseOrder).filter(
        PurchaseOrder.purchase_order_id == purchase_order_id,
        PurchaseOrder.warehouse_id == current_user.get("warehouse_id"),
    ).with_for_update().first()
    if purchase_order is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if purchase_order.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending purchase orders can be cancelled")
    purchase_order.status = "cancelled"
    log_activity(db, current_user["user_id"], current_user["username"], "CANCEL_PURCHASE_ORDER", f"Cancelled purchase order #{purchase_order_id}.")
    if purchase_order.created_by != current_user["user_id"]:
        create_notification(db, purchase_order.created_by, "Purchase order cancelled", f"Purchase order #{purchase_order_id} was cancelled.", "purchase_order_cancelled")
    db.commit()
    return {"purchase_order_id": purchase_order_id, "status": purchase_order.status}