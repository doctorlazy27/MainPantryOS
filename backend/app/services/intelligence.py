from datetime import date, datetime, timedelta
from math import ceil
import logging

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.batch import Batch
from app.models.inventory import Inventory
from app.models.order import SalesOrder
from app.models.order_item import SalesOrderItem
from app.models.product import Product
from app.models.inventory_recommendation import InventoryRecommendation
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.notification import create_notification_once
from app.services.ai_assistant import suggest_inventory_actions
from app.services.ai_provider import AIProviderError

logger = logging.getLogger(__name__)


def calculate_inventory_intelligence(db: Session, warehouse_id: int, today: date | None = None) -> list[dict]:
    current_day = today or date.today()
    expiry_limit = current_day + timedelta(days=7)
    cutoff = datetime.utcnow() - timedelta(days=30)
    results = []

    for product in db.query(Product).filter(Product.warehouse_id == warehouse_id).all():
        inventory_rows = db.query(Inventory).filter(
            Inventory.product_id == product.product_id,
            Inventory.warehouse_id == warehouse_id,
        ).all()
        current_quantity = sum(row.quantity for row in inventory_rows)
        recent_demand = db.query(SalesOrderItem.quantity).join(
            SalesOrder, SalesOrderItem.order_id == SalesOrder.order_id
        ).filter(
            SalesOrderItem.product_id == product.product_id,
            SalesOrder.warehouse_id == warehouse_id,
            SalesOrder.created_at >= cutoff,
            SalesOrder.status.notin_({"rejected", "cancelled"}),
        ).all()
        average_daily_demand = sum(quantity for (quantity,) in recent_demand) / 30
        days_remaining = round(current_quantity / average_daily_demand, 1) if average_daily_demand else None
        stockout_risk = "HIGH" if days_remaining is not None and days_remaining <= 3 else "MEDIUM" if days_remaining is not None and days_remaining <= 7 else "LOW"
        projected_requirement = ceil(average_daily_demand * 14)
        recommended_reorder = max(product.reorder_level, projected_requirement) - current_quantity
        expiry_rows = db.query(Inventory, Batch).join(
            Batch, Inventory.batch_id == Batch.batch_id
        ).filter(
            Inventory.product_id == product.product_id,
            Inventory.warehouse_id == warehouse_id,
            Inventory.quantity > 0,
            Batch.expiry_date >= current_day,
            Batch.expiry_date <= expiry_limit,
        ).all()
        waste_surplus = 0
        waste_inventory_ids = []
        for batch_inventory, batch in expiry_rows:
            days_to_expiry = max((batch.expiry_date - current_day).days, 1)
            surplus = max(batch_inventory.quantity - ceil(average_daily_demand * days_to_expiry), 0)
            waste_surplus += surplus
            if surplus > 0:
                waste_inventory_ids.append(batch_inventory.inventory_id)
        waste_risk = "HIGH" if waste_surplus > 0 else "MEDIUM" if expiry_rows else "LOW"
        if current_quantity > 0 or recent_demand:
            results.append({
                "product_id": product.product_id,
                "product_name": product.name,
                "unit": product.unit,
                "warehouse_id": warehouse_id,
                "current_stock": current_quantity,
                "average_daily_demand": round(average_daily_demand, 2),
                "estimated_days_remaining": days_remaining,
                "stockout_risk": stockout_risk,
                "waste_risk": waste_risk,
                "potential_surplus": waste_surplus,
                "recommended_reorder": max(recommended_reorder, 0),
                "expiry_inventory_ids": [row.inventory_id for row, _batch in expiry_rows],
                "waste_inventory_ids": waste_inventory_ids,
                "recommendation": "Prioritize the earliest-expiring batch" if expiry_rows else f"Reorder {max(recommended_reorder, 0)} {product.unit}" if recommended_reorder > 0 else "Stock levels are currently healthy",
            })
    return results


def process_inventory_intelligence(db: Session) -> dict[str, int]:
    if db.bind and db.bind.dialect.name == "postgresql":
        locked = db.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": 774322}).scalar()
        if not locked:
            return {"evaluated": 0, "notifications": 0, "skipped": 1}
    evaluated = 0
    notifications = 0
    ai_suggestions = 0
    for warehouse_id, in db.query(Warehouse.warehouse_id).all():
        results = calculate_inventory_intelligence(db, warehouse_id)
        evaluated += len(results)
        for result in results:
            recipients = db.query(User).filter(
                User.warehouse_id == warehouse_id,
                User.role.in_({"manager", "warehouse_worker"}),
            ).all()
            risk_period = date.today().isoformat()
            if result["stockout_risk"] == "HIGH" and result["estimated_days_remaining"] is not None:
                message = f"Stockout risk: {result['product_name']} is predicted to run out in approximately {result['estimated_days_remaining']} days at warehouse {warehouse_id}."
                for user in [recipient for recipient in recipients if recipient.role == "manager"]:
                    notification = create_notification_once(db, user.user_id, "High stockout risk", message, "inventory_stockout_risk", f"stockout:{result['product_id']}:{warehouse_id}:{risk_period}")
                    notifications += int(notification.notification_id is None)
            if result["waste_risk"] == "HIGH":
                message = f"High waste risk: {result['potential_surplus']} units of {result['product_name']} may remain unused before expiry at warehouse {warehouse_id}."
                for inventory_id in result["waste_inventory_ids"]:
                    for user in recipients:
                        notification = create_notification_once(db, user.user_id, "High waste risk", message, "inventory_waste_risk", f"waste:{inventory_id}:{risk_period}")
                        notifications += int(notification.notification_id is None)
            if result["recommended_reorder"] > 0:
                recommendation_key = f"reorder:{result['product_id']}:{warehouse_id}:{risk_period}"
                if db.query(InventoryRecommendation).filter(InventoryRecommendation.recommendation_key == recommendation_key).first() is None:
                    db.add(InventoryRecommendation(
                        recommendation_key=recommendation_key,
                        product_id=result["product_id"],
                        warehouse_id=warehouse_id,
                        recommendation_type="REORDER",
                        current_stock=result["current_stock"],
                        average_daily_demand=result["average_daily_demand"],
                        recommended_quantity=result["recommended_reorder"],
                        reason=f"Projected shortage based on recent demand; {result['product_name']} needs replenishment.",
                    ))
                message = f"Reorder recommended for {result['product_name']}: {result['recommended_reorder']} {result['unit']}. Current stock is {result['current_stock']}; average demand is {result['average_daily_demand']} per day."
                for user in [recipient for recipient in recipients if recipient.role == "manager"]:
                    notification = create_notification_once(db, user.user_id, "Reorder recommendation", message, "inventory_reorder_recommendation", recommendation_key)
                    notifications += int(notification.notification_id is None)
        try:
            suggestions = suggest_inventory_actions(results)
        except AIProviderError:
            logger.exception("AI inventory suggestions unavailable for warehouse %s", warehouse_id)
            suggestions = []
        managers = db.query(User).filter(User.warehouse_id == warehouse_id, User.role == "manager").all()
        workers = db.query(User).filter(User.warehouse_id == warehouse_id, User.role == "warehouse_worker").all()
        results_by_product = {result["product_id"]: result for result in results}
        for suggestion in suggestions:
            result = results_by_product[suggestion["product_id"]]
            if suggestion["action"] == "ORDER_REVIEW":
                recipients = managers
                title = f"AI flagged reorder review ({suggestion['priority'].lower()})"
                message = (
                    f"Review replenishment for {result['product_name']}: the rule-based reorder estimate is "
                    f"{result['recommended_reorder']} {result['unit']} at current stock {result['current_stock']}. "
                    "AI prioritized this review; it did not create an order."
                )
            else:
                recipients = managers + workers
                title = f"AI suggested inventory check ({suggestion['priority'].lower()})"
                message = (
                    f"Manually verify {result['product_name']} stock and expiry records. "
                    f"Current recorded stock is {result['current_stock']} {result['unit']}; "
                    f"stockout risk is {result['stockout_risk'].lower()} and waste risk is {result['waste_risk'].lower()}."
                )
            for recipient in recipients:
                notification = create_notification_once(
                    db,
                    recipient.user_id,
                    title,
                    message,
                    "ai_inventory_suggestion",
                    f"ai-inventory:{warehouse_id}:{result['product_id']}:{suggestion['action']}:{date.today().isoformat()}",
                )
                notifications += int(notification.notification_id is None)
            ai_suggestions += 1
    db.commit()
    return {"evaluated": evaluated, "notifications": notifications, "ai_suggestions": ai_suggestions}