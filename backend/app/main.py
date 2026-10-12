import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.routers.products import router as products_router
from sqlalchemy import text
from app.database import SessionLocal, engine
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.routers.warehouses import router as warehouses_router
from app.routers.customers import router as customers_router
from app.routers.stock_transfers import router as stock_transfers_router
from app.models.inventory import Inventory
from app.models.boxed_unit import BoxedUnit
from app.models.inventory_movement import InventoryMovement
from app.routers.inventory import router as inventory_router
from app.models.batch import Batch
from app.routers.batches import router as batches_router
from app.models.user import User
from app.routers.users import router as users_router
from app.models.customer import Customer
from app.routers.customers import router as customers_router
from app.models.order import SalesOrder
from app.models.order_item import SalesOrderItem
from app.routers.orders import router as orders_router
from app.models.supplier import Supplier
from app.routers.suppliers import router as suppliers_router
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.routers.purchase_orders import router as purchase_orders_router
from app.models.activity_log import ActivityLog
from app.routers.activity import router as activity_router
from app.models.notification import Notification
from app.models.message import Message
from app.models.inventory_addition_request import InventoryAdditionRequest
from app.models.warehouse_request import WarehouseRequest
from app.routers.notifications import router as notifications_router
from app.models.invoice import Invoice
from app.models.auth_session import AuthSession
from app.models.auth_otp import AuthOtp
from app.routers.invoices import router as invoices_router
from app.routers.internal_jobs import router as internal_jobs_router
from app.models.inventory_recommendation import InventoryRecommendation
from app.routers.recommendations import router as recommendations_router
from app.routers.counter import router as counter_router
from app.services.expiry import process_expiry
from app.services.intelligence import process_inventory_intelligence
from app.routers.dashboard import router as dashboard_router

logger = logging.getLogger(__name__)


def run_expiry_job() -> None:
    db = SessionLocal()
    try:
        process_expiry(db)
    except Exception:
        db.rollback()
        logger.exception("Local expiry job failed")
    finally:
        db.close()


def run_inventory_intelligence_job() -> None:
    db = SessionLocal()
    try:
        process_inventory_intelligence(db)
    except Exception:
        db.rollback()
        logger.exception("Local inventory intelligence job failed")
    finally:
        db.close()


async def expiry_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        await asyncio.to_thread(run_expiry_job)


async def inventory_intelligence_loop() -> None:
    await asyncio.sleep(60)
    while True:
        await asyncio.to_thread(run_inventory_intelligence_job)
        await asyncio.sleep(24 * 60 * 60)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    tasks = []
    if os.getenv("ENABLE_LOCAL_EXPIRY_LOOP", "true").lower() == "true":
        await asyncio.to_thread(run_expiry_job)
        tasks.append(asyncio.create_task(expiry_loop()))
    if os.getenv("ENABLE_LOCAL_INVENTORY_AI_LOOP", "true").lower() == "true":
        tasks.append(asyncio.create_task(inventory_intelligence_loop()))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

app = FastAPI(
    title="Food Warehouse Management System",
    description="Backend API for managing food warehouse operations.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

cors_origins = os.getenv("CORS_ORIGINS") or (
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:8081,http://127.0.0.1:8081,https://localhost"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(products_router)
app.include_router(customers_router)
app.include_router(warehouses_router)
app.include_router(inventory_router)
app.include_router(batches_router)
app.include_router(users_router)
app.include_router(suppliers_router)
app.include_router(purchase_orders_router)
app.include_router(orders_router)
app.include_router(invoices_router)
app.include_router(stock_transfers_router)
app.include_router(activity_router)
app.include_router(notifications_router)
app.include_router(dashboard_router)
app.include_router(internal_jobs_router)
app.include_router(recommendations_router)
app.include_router(counter_router)

@app.get("/")
def root():
    return {
        "message": "Food Warehouse Management System API is running"
    }


@app.get("/health")
def health_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "unavailable"},
        )

    return {"status": "healthy", "database": "connected"}

@app.get("/database-test", include_in_schema=False)
def database_test():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))

        return {
            "database": "connected",
            "result": result.scalar()
        }


