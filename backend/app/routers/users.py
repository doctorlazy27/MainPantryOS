from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.auth.security import verify_password
from app.database import get_db
from app.models.activity_log import ActivityLog
from app.models.invoice import Invoice
from app.models.notification import Notification
from app.models.order import SalesOrder
from app.models.purchase_order import PurchaseOrder
from app.models.stock_transfer import StockTransfer
from app.models.user import User
from app.models.auth_session import AuthSession
from app.models.message import Message
from app.models.counter_allocation import CounterAllocation
from app.models.counter_sale import CounterSale
from app.models.inventory_addition_request import InventoryAdditionRequest
from app.models.warehouse_request import WarehouseRequest
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_recommendation import InventoryRecommendation
from app.models.order_pick_scan import OrderPickScan
from app.models.temperature_log import TemperatureLog
from app.schemas.user import UserDelete


router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


@router.get("/")
def get_users(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("manage_users"))):
    users = db.query(User).filter(User.warehouse_id == current_user.get("warehouse_id")).all()

    return {
        "users": [
            {
                "user_id": user.user_id,
                "username": user.username,
                "full_name": user.full_name,
                "role": user.role,
                "warehouse_id": user.warehouse_id,
            }
            for user in users
        ]
    }


@router.api_route("/{user_id}", methods=["DELETE"], include_in_schema=True)
@router.post("/{user_id}/remove", include_in_schema=True)
def remove_user(
    user_id: int,
    deletion: UserDelete | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("manage_users"))
):
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.warehouse_id != current_user.get("warehouse_id"):
        raise HTTPException(status_code=403, detail="You can only manage users in your warehouse")
    if user_id != current_user["user_id"] and user.role == "manager":
        raise HTTPException(status_code=403, detail="Manager accounts cannot be removed")

    if user_id == current_user["user_id"]:
        if user.role != "manager":
            raise HTTPException(status_code=403, detail="Only manager accounts can self-delete")

        manager_count = db.query(User).filter(User.role == "manager", User.warehouse_id == current_user.get("warehouse_id")).count()
        if manager_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete account. A duplicate manager account must exist and be approved first.",
            )

        if deletion is None or not verify_password(deletion.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Incorrect password")

    history_owner_id = current_user["user_id"]
    if user_id == current_user["user_id"]:
        history_owner = db.query(User).filter(
            User.role == "manager",
            User.warehouse_id == current_user.get("warehouse_id"),
            User.user_id != user_id,
        ).first()
        if history_owner is None:
            raise HTTPException(status_code=400, detail="Cannot delete account. A duplicate manager account must exist and be approved first.")
        history_owner_id = history_owner.user_id

    # Preserve operational history under the manager who performed the removal.
    db.query(SalesOrder).filter(SalesOrder.created_by == user_id).update(
        {SalesOrder.created_by: history_owner_id}, synchronize_session=False
    )
    db.query(PurchaseOrder).filter(PurchaseOrder.created_by == user_id).update(
        {PurchaseOrder.created_by: history_owner_id}, synchronize_session=False
    )
    db.query(StockTransfer).filter(StockTransfer.created_by == user_id).update(
        {StockTransfer.created_by: history_owner_id}, synchronize_session=False
    )
    db.query(CounterAllocation).filter(CounterAllocation.requested_by == user_id).update(
        {CounterAllocation.requested_by: history_owner_id}, synchronize_session=False
    )
    db.query(CounterSale).filter(CounterSale.worker_id == user_id).update(
        {CounterSale.worker_id: history_owner_id}, synchronize_session=False
    )
    db.query(InventoryAdditionRequest).filter(InventoryAdditionRequest.requested_by == user_id).update(
        {InventoryAdditionRequest.requested_by: history_owner_id}, synchronize_session=False
    )
    db.query(OrderPickScan).filter(OrderPickScan.actor_id == user_id).update(
        {OrderPickScan.actor_id: history_owner_id, OrderPickScan.actor_name: user.full_name}, synchronize_session=False
    )
    db.query(TemperatureLog).filter(TemperatureLog.recorded_by == user_id).update(
        {TemperatureLog.recorded_by: None}, synchronize_session=False
    )
    db.query(InventoryAdditionRequest).filter(InventoryAdditionRequest.reviewed_by == user_id).update(
        {InventoryAdditionRequest.reviewed_by: None}, synchronize_session=False
    )
    db.query(WarehouseRequest).filter(WarehouseRequest.requested_by == user_id).update(
        {WarehouseRequest.requested_by: history_owner_id}, synchronize_session=False
    )
    db.query(InventoryMovement).filter(InventoryMovement.actor_id == user_id).update(
        {InventoryMovement.actor_id: None}, synchronize_session=False
    )
    db.query(InventoryRecommendation).filter(InventoryRecommendation.reviewed_by == user_id).update(
        {InventoryRecommendation.reviewed_by: None}, synchronize_session=False
    )
    db.query(CounterAllocation).filter(CounterAllocation.reviewed_by == user_id).update(
        {CounterAllocation.reviewed_by: None}, synchronize_session=False
    )
    db.query(WarehouseRequest).filter(WarehouseRequest.approved_by == user_id).update(
        {WarehouseRequest.approved_by: None}, synchronize_session=False
    )
    db.query(SalesOrder).filter(SalesOrder.confirmed_by == user_id).update(
        {SalesOrder.confirmed_by: None}, synchronize_session=False
    )
    db.query(Invoice).filter(Invoice.sent_by == user_id).update(
        {Invoice.sent_by: None}, synchronize_session=False
    )
    db.query(Invoice).filter(Invoice.confirmed_by == user_id).update(
        {Invoice.confirmed_by: None}, synchronize_session=False
    )
    db.query(ActivityLog).filter(ActivityLog.user_id == user_id).update(
        {ActivityLog.user_id: history_owner_id}, synchronize_session=False
    )
    db.query(Notification).filter(Notification.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(AuthSession).filter(AuthSession.user_id == user_id).delete(
        synchronize_session=False
    )

    message_ids = [message_id for (message_id,) in db.query(Message.message_id).filter(
        or_(Message.sender_id == user_id, Message.recipient_id == user_id)
    ).all()]
    if message_ids:
        db.query(Message).filter(Message.reply_to_id.in_(message_ids)).update(
            {Message.reply_to_id: None}, synchronize_session=False
        )
        db.query(Message).filter(Message.message_id.in_(message_ids)).delete(
            synchronize_session=False
        )

    db.delete(user)
    db.commit()

    return {
        "message": "User removed successfully",
        "user_id": user_id,
        "removed_by": current_user["username"],
    }