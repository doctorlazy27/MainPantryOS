import os
from datetime import date, datetime, timedelta
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-router-registration-secret")

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.auth.dependencies import get_current_user
from app.auth.permissions import has_permission
from app.auth.roles import UserRole
from app.auth.security import create_access_token, hash_password, verify_password
from app.auth.router import approve_registration_request, confirm_password_reset, get_roles, logout_user
from app.models.auth_session import AuthSession
from app.models.auth_otp import AuthOtp
from app.models.activity_log import ActivityLog
from app.models.batch import Batch
from app.models.boxed_unit import BoxedUnit
from app.models.customer import Customer
from app.models.counter_inventory import CounterInventory
from app.models.counter_allocation import CounterAllocation
from app.models.counter_sale import CounterSale, CounterSaleItem
from app.models.inventory import Inventory
from app.models.inventory_addition_request import InventoryAdditionRequest
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_recommendation import InventoryRecommendation
from app.models.notification import Notification
from app.models.order import SalesOrder
from app.models.order_item import SalesOrderItem
from app.models.order_inventory_reservation import OrderInventoryReservation
from app.models.order_pick_scan import OrderPickScan
from app.models.temperature_log import TemperatureLog
from app.models.warehouse_request import WarehouseRequest
from app.models.registration_request import RegistrationRequest
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.stock_transfer import StockTransfer
from app.models.user import User
from app.models.warehouse import Warehouse
import app.main as main_module
from app.main import app
from app.routers import internal_jobs
from app.routers.internal_jobs import process_expiry_job, require_job_secret
from app.services.inventory_guard import require_available_batch
from app.services.expiry import process_expiry
import app.services.ai_assistant as ai_assistant
import app.services.intelligence as intelligence_module
import app.routers.counter as counter_module
import app.routers.invoices as invoice_module
from app.services.ai_assistant import suggest_inventory_actions
from app.services.intelligence import process_inventory_intelligence
from app.services.invoice_reports import build_invoice_report, period_window
from app.services import ai_provider
from app.routers.orders import _fefo_plan, approve_order, cancel_order, confirm_order_receipt, create_order, fulfill_order, scan_order_pick
from app.routers.recommendations import review_recommendation
from app.routers.invoices import confirm_invoice, generate_invoice, get_invoice, get_invoices, send_invoice, summarize_invoice_period
from app.routers.inventory import approve_inventory_addition, confirm_putaway, receive_inventory_addition, record_storage_temperature, reject_inventory_addition, request_inventory_addition
from app.routers.counter import checkout, lookup_counter_barcode
from app.routers.counter import warehouse_copilot
from app.routers.stock_transfers import list_stock_transfers
from app.routers.users import remove_user
from app.routers.purchase_orders import cancel_purchase_order, receive_purchase_order
from app.schemas.counter import CheckoutCreate, CheckoutItem
from app.schemas.inventory_addition_approval import InventoryReceiptDetails
from app.schemas.inventory_addition_request import InventoryAdditionRequestCreate
from app.schemas.order import OrderItemCreate, SalesOrderCreate
from app.schemas.warehouse_workflow import OrderPickScanCreate, PutawayConfirm, TemperatureCheckCreate
from app.schemas.inventory_recommendation import RecommendationReview
from app.schemas.user import PasswordResetConfirm
from app.schemas.receiving import ReceiveItem, ReceivePurchaseOrder
from app.services.cold_chain import temperature_is_safe
from app.services.ocr_provider import normalize_textract_expense


from sqlalchemy import event


@event.listens_for(Product, "before_insert")
def _default_test_warehouse(_mapper, _connection, product):
    # Fixtures predate warehouse-scoped products; the first test warehouse is id 1.
    if product.warehouse_id is None:
        product.warehouse_id = 1


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def seed_expiring_inventory(db):
    warehouse = Warehouse(name="Test warehouse", location="Test")
    worker = User(username="worker", full_name="Worker", role="warehouse_worker", password_hash="x", warehouse_id=1)
    manager = User(username="manager", full_name="Manager", role="manager", password_hash="x", warehouse_id=1)
    product = Product(name="Milk", category="Dairy", quantity=0, unit="units", price=2, units_per_box=1)
    db.add(warehouse)
    db.flush()
    worker.warehouse_id = warehouse.warehouse_id
    manager.warehouse_id = warehouse.warehouse_id
    db.add_all([worker, manager, product])
    db.flush()
    batch = Batch(product_id=product.product_id, batch_number="EXPIRED-1", manufacturing_date=date.today() - timedelta(days=8), expiry_date=date.today() - timedelta(days=1))
    db.add(batch)
    db.flush()
    inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=100)
    db.add(inventory)
    db.commit()
    return warehouse, product, batch, inventory


def test_core_workflow_routers_are_registered():
    paths = set(app.openapi()["paths"])
    assert {"/customers/", "/orders/", "/invoices/"} <= paths
    assert "/stock-transfers/" not in paths


def test_invoice_report_periods_use_calendar_windows():
    current_day = date(2026, 9, 27)
    assert period_window("weekly", current_day) == (date(2026, 9, 21), date(2026, 9, 28), date(2026, 9, 14), date(2026, 9, 21))
    assert period_window("monthly", current_day) == (date(2026, 9, 1), date(2026, 10, 1), date(2026, 8, 1), date(2026, 9, 1))
    assert period_window("yearly", current_day) == (date(2026, 1, 1), date(2027, 1, 1), date(2025, 1, 1), date(2026, 1, 1))


def test_ai_provider_is_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    assert ai_provider.complete("system", "user") is None


def test_ai_provider_uses_backend_configuration(monkeypatch):
    monkeypatch.setenv("AI_API_URL", "https://model.example/v1/chat/completions")
    monkeypatch.setenv("AI_API_KEY", "test-only-key")
    monkeypatch.setenv("AI_MODEL", "free-test-model")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "grounded summary"}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(ai_provider.httpx, "post", fake_post)

    result = ai_provider.complete("system rule", "warehouse data")

    assert result == "grounded summary"
    assert captured["url"] == "https://model.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-only-key"
    assert captured["json"]["model"] == "free-test-model"


def test_cors_origins_are_explicit_and_include_capacitor_hosts():
    assert "https://localhost" in main_module.cors_origins
    assert "http://localhost" in main_module.cors_origins
    assert "*" not in main_module.cors_origins


def test_cors_origins_are_explicit_and_include_capacitor_hosts():
    assert "https://localhost" in main_module.cors_origins
    assert "http://localhost" in main_module.cors_origins
    assert "*" not in main_module.cors_origins


def test_manager_has_sales_workflow_and_signup_hides_legacy_role():
    assert has_permission(UserRole.MANAGER, "create_orders")
    assert has_permission(UserRole.MANAGER, "confirm_order_receipt")
    assert has_permission(UserRole.MANAGER, "send_invoices")
    assert has_permission(UserRole.MANAGER, "confirm_invoices")
    assert has_permission(UserRole.MANAGER, "request_stock_transfer")
    assert has_permission(UserRole.MANAGER, "approve_sales_orders")
    assert has_permission(UserRole.MANAGER, "view_invoices")
    assert has_permission(UserRole.MANAGER, "request_store_orders")
    assert has_permission(UserRole.MANAGER, "receive_store_orders")
    assert has_permission(UserRole.MANAGER, "manage_cashiers")
    assert has_permission(UserRole.MANAGER, "approve_inventory_requests")
    for retired in ("request_warehouse_stock", "update_inventory", "receive_purchase_orders", "review_inventory_recommendations", "create_purchase_orders", "checkout_counter", "request_counter_allocation"):
        assert not has_permission(UserRole.MANAGER, retired)
    assert has_permission(UserRole.WAREHOUSE_WORKER, "dispatch_store_orders")
    assert has_permission(UserRole.WAREHOUSE_WORKER, "update_inventory")
    assert not has_permission(UserRole.WAREHOUSE_WORKER, "checkout_counter")
    assert not has_permission(UserRole.WAREHOUSE_WORKER, "approve_inventory_requests")
    assert has_permission(UserRole.CASHIER, "checkout_counter")
    assert not has_permission(UserRole.CASHIER, "view_orders")
    assert not has_permission(UserRole.CASHIER, "view_counter_sales")
    assert not has_permission(UserRole.WAREHOUSE_WORKER, "view_customers")
    assert not has_permission(UserRole.WAREHOUSE_WORKER, "view_suppliers")
    assert not has_permission(UserRole.WAREHOUSE_WORKER, "view_stock_transfers")
    assert set(get_roles()["roles"]) == {UserRole.MANAGER.value, UserRole.WAREHOUSE_WORKER.value}
    assert not has_permission(UserRole.WAREHOUSE_WORKER, "approve_sales_orders")
    assert not has_permission(UserRole.WAREHOUSE_WORKER, "view_invoices")
    assert has_permission(UserRole.MANAGER, "view_ai_copilot") and has_permission(UserRole.WAREHOUSE_WORKER, "view_ai_copilot")


def test_logout_revokes_only_the_current_session(db):
    user = User(username="logout-user", full_name="Logout User", email="logout@example.com", role="manager", password_hash="x")
    db.add(user)
    db.flush()
    current = AuthSession(session_id=str(uuid4()), user_id=user.user_id)
    other = AuthSession(session_id=str(uuid4()), user_id=user.user_id)
    db.add_all([current, other])
    db.commit()

    response = logout_user(db, {"user_id": user.user_id, "session_id": current.session_id})

    assert response["message"] == "Session revoked"
    assert db.query(AuthSession).filter_by(user_id=user.user_id).all() == [other]


def test_password_reset_revokes_all_active_sessions(db):
    user = User(username="reset-user", full_name="Reset User", email="reset@example.com", role="manager", password_hash=hash_password("old-password"))
    db.add(user)
    db.flush()
    db.add_all([
        AuthSession(session_id=str(uuid4()), user_id=user.user_id),
        AuthSession(session_id=str(uuid4()), user_id=user.user_id),
        AuthOtp(email=user.email, purpose="password_reset", code_hash=hash_password("123456"), expires_at=datetime.utcnow() + timedelta(minutes=5)),
    ])
    db.commit()

    response = confirm_password_reset(PasswordResetConfirm(email=user.email, otp="123456", new_password="new-password"), db)

    assert response["message"] == "Password updated. You can now sign in."
    assert db.query(AuthSession).filter_by(user_id=user.user_id).count() == 0
    assert verify_password("new-password", user.password_hash)


def test_manager_cannot_approve_legacy_role_signup(db):
    warehouse = Warehouse(name="Legacy signup warehouse", location="Test")
    manager = User(username="legacy-review-manager", full_name="Manager", role="manager", password_hash="x")
    db.add_all([warehouse, manager])
    db.flush()
    manager.warehouse_id = warehouse.warehouse_id
    request = RegistrationRequest(username="legacy-sales", full_name="Old Sales Signup", email="old-sales@example.com", role="salesperson", password_hash="x", status="pending", warehouse_id=warehouse.warehouse_id)
    db.add(request)
    db.commit()
    actor = {"user_id": manager.user_id, "username": manager.full_name, "role": manager.role, "warehouse_id": warehouse.warehouse_id}

    with pytest.raises(HTTPException) as error:
        approve_registration_request(request.request_id, db, actor)

    assert error.value.status_code == 409
    assert request.status == "pending"
    assert db.query(User).filter_by(username="legacy-sales").first() is None


def test_ai_copilot_uses_warehouse_fallback_without_provider(db, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "")
    monkeypatch.setenv("AI_MODEL", "")
    warehouse = Warehouse(name="Copilot warehouse", location="Test")
    db.add(warehouse)
    db.commit()
    actor = {"user_id": 1, "username": "Worker", "role": "warehouse_worker", "warehouse_id": warehouse.warehouse_id}

    result = warehouse_copilot("What needs attention?", db, actor)

    assert result["ai_powered"] is False
    assert "0 counter replenishment" in result["answer"]
    assert result["priorities"] == ["No urgent counter or expiry risks are currently reported."]


def test_ai_copilot_uses_provider_answer_when_available(db, monkeypatch):
    warehouse = Warehouse(name="Model copilot warehouse", location="Test")
    db.add(warehouse)
    db.commit()
    monkeypatch.setattr(counter_module, "process_expiry", lambda _db: None)
    monkeypatch.setattr(counter_module, "answer_warehouse_question", lambda question, _context: f"Grounded answer: {question}")
    actor = {"user_id": 1, "username": "Manager", "role": "manager", "warehouse_id": warehouse.warehouse_id}

    result = warehouse_copilot("What should I check?", db, actor)

    assert result["ai_powered"] is True
    assert result["answer"] == "Grounded answer: What should I check?"


def test_invoice_report_summary_uses_model_when_available(db, monkeypatch):
    warehouse = Warehouse(name="Report warehouse", location="Test")
    db.add(warehouse)
    db.commit()
    monkeypatch.setattr(invoice_module, "summarize_invoice_report", lambda _report: "Two invoices are awaiting review.")
    actor = {"user_id": 1, "username": "Manager", "role": "manager", "warehouse_id": warehouse.warehouse_id}

    result = summarize_invoice_period("monthly", db, actor)

    assert result == {"summary": "Two invoices are awaiting review.", "ai_powered": True}


def test_sales_order_completes_role_handoff_loop(db, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "")
    monkeypatch.setenv("AI_MODEL", "")
    warehouse = Warehouse(name="Workflow warehouse", location="Test")
    db.add(warehouse)
    db.flush()
    manager = User(username="workflow-manager", full_name="Manager", role="manager", password_hash="x", warehouse_id=warehouse.warehouse_id)
    worker = User(username="workflow-worker", full_name="Worker", role="warehouse_worker", password_hash="x", warehouse_id=warehouse.warehouse_id)
    product = Product(name="Workflow rice", category="Dry goods", quantity=0, unit="kg", price=2, units_per_box=1)
    customer = Customer(name="Workflow buyer", phone="000", warehouse_id=warehouse.warehouse_id)
    db.add_all([manager, worker, product, customer])
    db.flush()
    batch = Batch(product_id=product.product_id, batch_number="FLOW-1", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=20))
    db.add(batch)
    db.flush()
    inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=12)
    db.add(inventory)
    db.flush()
    db.add(BoxedUnit(inventory_id=inventory.inventory_id, scanned_code="FLOW-CODE", units=12, remaining_units=12))
    db.commit()

    def actor(user):
        return {"user_id": user.user_id, "username": user.full_name, "role": user.role, "warehouse_id": warehouse.warehouse_id}

    request = SalesOrderCreate(customer_id=customer.customer_id, items=[OrderItemCreate(product_id=product.product_id, quantity=5)])
    created = create_order(request, db, actor(manager))
    approved = approve_order(created["order_id"], db, actor(manager))
    picked = scan_order_pick(created["order_id"], OrderPickScanCreate(scanned_code="FLOW-CODE", quantity=5, event_key="FLOW-PICK-1"), db, actor(worker))
    fulfilled = fulfill_order(created["order_id"], db, actor(worker))
    with pytest.raises(HTTPException) as repeated_fulfillment:
        fulfill_order(created["order_id"], db, actor(worker))
    confirmed = confirm_order_receipt(created["order_id"], db, actor(manager))
    generated_invoice = generate_invoice(created["order_id"], db, actor(manager))
    sent_invoice = send_invoice(generated_invoice["invoice_id"], db, actor(manager))
    final_invoice = confirm_invoice(generated_invoice["invoice_id"], db, actor(manager))

    other_worker = User(username="other-workflow-worker", full_name="Other worker", role="warehouse_worker", password_hash="x", warehouse_id=warehouse.warehouse_id)
    other_customer = Customer(name="Other buyer", phone="111")
    db.add_all([other_worker, other_customer])
    db.flush()
    other_order = SalesOrder(customer_id=other_customer.customer_id, created_by=other_worker.user_id, warehouse_id=warehouse.warehouse_id, status="confirmed")
    db.add(other_order)
    db.flush()
    db.add(SalesOrderItem(order_id=other_order.order_id, product_id=product.product_id, quantity=1, unit_price=product.price))
    other_invoice = Invoice(order_id=other_order.order_id, customer_id=other_customer.customer_id, generated_by=other_worker.username, total_amount=product.price, status="generated")
    db.add(other_invoice)
    db.commit()
    manager_invoices = get_invoices(db, actor(manager))["invoices"]
    manager_report = build_invoice_report(db, "weekly", actor(manager))
    local_summary = summarize_invoice_period("weekly", db, actor(manager))

    assert created["status"] == "pending"
    assert approved["status"] == "approved"
    assert picked["picked_quantity"] == 5
    assert fulfilled["status"] == "fulfilled"
    assert repeated_fulfillment.value.status_code == 400
    assert confirmed["status"] == "confirmed"
    assert generated_invoice["status"] == "generated"
    assert sent_invoice["status"] == "sent"
    assert final_invoice["status"] == "confirmed"
    assert len(manager_invoices) == 2
    assert manager_report["invoice_count"] == 2
    assert local_summary["ai_powered"] is False
    assert inventory.quantity == 7
    assert db.query(InventoryMovement).filter(InventoryMovement.movement_type == "SOLD").count() == 1
    assert db.query(Invoice).filter(Invoice.order_id == created["order_id"]).count() == 1


def test_fulfillment_rejects_invalidated_pick_scans(db):
    warehouse = Warehouse(name="Invalid pick warehouse", location="Test")
    worker = User(username="invalid-pick-worker", full_name="Worker", role="warehouse_worker", password_hash="x")
    customer = Customer(name="Invalid pick buyer", phone="000")
    product = Product(name="Invalid pick product", category="General", quantity=0, unit="units", price=2, units_per_box=1)
    db.add_all([warehouse, worker, customer, product])
    db.flush()
    worker.warehouse_id = warehouse.warehouse_id
    batch = Batch(product_id=product.product_id, batch_number="INVALID-PICK-1", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=10), status="quarantined")
    db.add(batch)
    db.flush()
    inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=2, putaway_status="hold")
    order = SalesOrder(customer_id=customer.customer_id, created_by=worker.user_id, warehouse_id=warehouse.warehouse_id, status="approved", reservation_status="reserved")
    db.add_all([inventory, order])
    db.flush()
    db.add(SalesOrderItem(order_id=order.order_id, product_id=product.product_id, quantity=2, unit_price=product.price))
    db.add(OrderInventoryReservation(order_id=order.order_id, inventory_id=inventory.inventory_id, product_id=product.product_id, batch_id=batch.batch_id, warehouse_id=warehouse.warehouse_id, quantity=2))
    db.add(OrderPickScan(
        event_key="INVALID-PICK-EVENT",
        order_id=order.order_id,
        inventory_id=inventory.inventory_id,
        product_id=product.product_id,
        batch_id=batch.batch_id,
        scanned_code=batch.batch_number,
        quantity=2,
        is_valid=False,
        actor_id=worker.user_id,
    ))
    db.commit()

    actor = {"user_id": worker.user_id, "username": worker.full_name, "role": worker.role, "warehouse_id": warehouse.warehouse_id}
    with pytest.raises(HTTPException) as error:
        fulfill_order(order.order_id, db, actor)

    assert error.value.status_code == 400
    assert order.status == "approved"
    assert inventory.quantity == 2


def test_cold_chain_quarantine_releases_order_reservation_for_manager_resolution(db):
    warehouse = Warehouse(name="Reservation quarantine warehouse", location="Test")
    worker = User(username="reservation-quarantine-worker", full_name="Worker", role="warehouse_worker", password_hash="x")
    manager = User(username="reservation-quarantine-manager", full_name="Manager", role="manager", password_hash="x")
    customer = Customer(name="Reservation quarantine buyer", phone="000")
    product = Product(name="Reservation quarantine product", category="General", quantity=0, unit="units", price=2, units_per_box=1)
    db.add_all([warehouse, worker, manager, customer, product])
    db.flush()
    worker.warehouse_id = manager.warehouse_id = warehouse.warehouse_id
    batch = Batch(product_id=product.product_id, batch_number="RESERVATION-QC-1", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=10))
    db.add(batch)
    db.flush()
    inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=3, storage_zone="AMBIENT")
    order = SalesOrder(customer_id=customer.customer_id, created_by=manager.user_id, warehouse_id=warehouse.warehouse_id, status="approved", reservation_status="reserved")
    db.add_all([inventory, order])
    db.flush()
    reservation = OrderInventoryReservation(order_id=order.order_id, inventory_id=inventory.inventory_id, product_id=product.product_id, batch_id=batch.batch_id, warehouse_id=warehouse.warehouse_id, quantity=3)
    pick = OrderPickScan(event_key="RESERVATION-QC-EVENT", order_id=order.order_id, inventory_id=inventory.inventory_id, product_id=product.product_id, batch_id=batch.batch_id, scanned_code=batch.batch_number, quantity=1, actor_name=worker.full_name, actor_id=worker.user_id)
    db.add_all([reservation, pick])
    db.commit()
    actor = {"user_id": worker.user_id, "username": worker.full_name, "role": worker.role, "warehouse_id": warehouse.warehouse_id}

    result = record_storage_temperature(batch.batch_id, TemperatureCheckCreate(temperature_c=30), db, actor)

    assert result["within_range"] is False
    assert order.reservation_status == "short"
    assert reservation.status == "released"
    assert pick.is_valid is False


def test_approved_orders_reserve_stock_and_cancellation_releases_it(db):
    warehouse = Warehouse(name="Reservation warehouse", location="Test")
    manager = User(username="reservation-manager", full_name="Manager", role="manager", password_hash="x")
    worker = User(username="reservation-worker", full_name="Worker", role="warehouse_worker", password_hash="x")
    customer = Customer(name="Reservation buyer", phone="000")
    product = Product(name="Reserved product", category="General", quantity=0, unit="units", price=2, units_per_box=1)
    db.add_all([warehouse, manager, worker, customer, product])
    db.flush()
    manager.warehouse_id = worker.warehouse_id = warehouse.warehouse_id
    batch = Batch(product_id=product.product_id, batch_number="RESERVED-1", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=10))
    db.add(batch)
    db.flush()
    inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=5)
    db.add(inventory)
    first = SalesOrder(customer_id=customer.customer_id, created_by=manager.user_id, warehouse_id=warehouse.warehouse_id, status="pending")
    second = SalesOrder(customer_id=customer.customer_id, created_by=manager.user_id, warehouse_id=warehouse.warehouse_id, status="pending")
    db.add_all([first, second])
    db.flush()
    db.add_all([
        SalesOrderItem(order_id=first.order_id, product_id=product.product_id, quantity=4, unit_price=product.price),
        SalesOrderItem(order_id=second.order_id, product_id=product.product_id, quantity=4, unit_price=product.price),
    ])
    db.commit()
    actor = {"user_id": manager.user_id, "username": manager.full_name, "role": manager.role, "warehouse_id": warehouse.warehouse_id}

    approved = approve_order(first.order_id, db, actor)
    with pytest.raises(HTTPException) as error:
        approve_order(second.order_id, db, actor)

    assert approved["status"] == "approved"
    assert error.value.status_code == 400
    assert db.query(OrderInventoryReservation).filter_by(order_id=first.order_id, status="reserved").one().quantity == 4
    assert second.status == "pending"

    cancelled = cancel_order(first.order_id, db, actor)

    assert cancelled["status"] == "cancelled"
    assert db.query(OrderInventoryReservation).filter_by(order_id=first.order_id, status="reserved").count() == 0


def test_worker_removal_preserves_pick_history_and_clears_optional_actor_references(db):
    warehouse = Warehouse(name="Removal warehouse", location="Test")
    manager = User(username="removal-manager", full_name="Manager", role="manager", password_hash="x")
    worker = User(username="removal-worker", full_name="Worker", role="warehouse_worker", password_hash="x")
    customer = Customer(name="Removal buyer", phone="000")
    product = Product(name="Removal product", category="General", quantity=0, unit="units", price=2, units_per_box=1)
    db.add_all([warehouse, manager, worker, customer, product])
    db.flush()
    manager.warehouse_id = worker.warehouse_id = warehouse.warehouse_id
    batch = Batch(product_id=product.product_id, batch_number="REMOVAL-1", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=10))
    db.add(batch)
    db.flush()
    inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=1)
    order = SalesOrder(customer_id=customer.customer_id, created_by=manager.user_id, warehouse_id=warehouse.warehouse_id, status="approved", reservation_status="reserved")
    db.add_all([inventory, order])
    db.flush()
    pick = OrderPickScan(event_key="REMOVAL-EVENT", order_id=order.order_id, inventory_id=inventory.inventory_id, product_id=product.product_id, batch_id=batch.batch_id, scanned_code="REMOVAL-1", quantity=1, actor_name=worker.full_name, actor_id=worker.user_id)
    temperature = TemperatureLog(batch_id=batch.batch_id, inventory_id=inventory.inventory_id, warehouse_id=warehouse.warehouse_id, recorded_by=worker.user_id, stage="storage", storage_zone="AMBIENT", temperature_c=20, minimum_c=10, maximum_c=30, within_range=True)
    db.add_all([pick, temperature])
    db.commit()
    actor = {"user_id": manager.user_id, "username": manager.full_name, "role": manager.role, "warehouse_id": warehouse.warehouse_id}

    remove_user(worker.user_id, None, db, actor)

    assert db.query(User).filter_by(user_id=worker.user_id).first() is None
    assert db.query(OrderPickScan).filter_by(pick_scan_id=pick.pick_scan_id).one().actor_id == manager.user_id
    assert db.query(OrderPickScan).filter_by(pick_scan_id=pick.pick_scan_id).one().actor_name == "Worker"
    assert db.query(TemperatureLog).filter_by(temperature_log_id=temperature.temperature_log_id).one().recorded_by is None


def test_cold_chain_temperature_ranges():
    assert temperature_is_safe("AMBIENT", 20)
    assert temperature_is_safe("CHILLED", 4)
    assert temperature_is_safe("FROZEN", -20)
    assert not temperature_is_safe("CHILLED", 9)


def test_reorder_approval_creates_receivable_purchase_order(db):
    warehouse = Warehouse(name="Reorder warehouse", location="Test")
    manager = User(username="reorder-manager", full_name="Manager", role="manager", password_hash="x")
    product = Product(name="Reorder apples", category="Fruit", quantity=0, unit="kg", price=3.5)
    supplier = Supplier(name="Orchard supplier", phone="000")
    db.add_all([warehouse, manager, product, supplier])
    db.flush()
    manager.warehouse_id = warehouse.warehouse_id
    recommendation = InventoryRecommendation(
        recommendation_key="reorder-test-1",
        product_id=product.product_id,
        warehouse_id=warehouse.warehouse_id,
        recommendation_type="REORDER",
        current_stock=2,
        average_daily_demand=1.5,
        recommended_quantity=20,
        reason="Projected shortage",
    )
    db.add(recommendation)
    db.commit()
    actor = {"user_id": manager.user_id, "username": manager.username, "role": manager.role, "warehouse_id": warehouse.warehouse_id}

    result = review_recommendation(recommendation.recommendation_id, "approve", RecommendationReview(supplier_id=supplier.supplier_id), db, actor)
    purchase_order = db.query(PurchaseOrder).filter_by(purchase_order_id=result["purchase_order_id"]).one()
    item = db.query(PurchaseOrderItem).filter_by(purchase_order_id=purchase_order.purchase_order_id).one()

    assert result["status"] == "APPROVED"
    assert purchase_order.status == "pending"
    assert item.product_id == product.product_id
    assert item.quantity == 20
    assert item.unit_price == 3.5


def test_textract_expense_normalizer_extracts_reviewable_fields():
    response = {"ExpenseDocuments": [{
        "SummaryFields": [{"Type": {"Text": "VENDOR_NAME"}, "ValueDetection": {"Text": "Valley Foods"}}],
        "LineItemGroups": [{"LineItems": [{"LineItemExpenseFields": [
            {"Type": {"Text": "ITEM"}, "ValueDetection": {"Text": "Milk"}},
            {"Type": {"Text": "QUANTITY"}, "ValueDetection": {"Text": "12"}},
            {"Type": {"Text": "LOT_NUMBER"}, "ValueDetection": {"Text": "MLK-42"}},
            {"Type": {"Text": "EXPIRY_DATE"}, "ValueDetection": {"Text": "2026-11-01"}},
        ]}]}],
    }]}
    result = normalize_textract_expense(response)
    assert result["vendor"] == "Valley Foods"
    assert result["items"][0]["lot_number"] == "MLK-42"
    assert result["items"][0]["expiry_date"] == "2026-11-01"
    assert result["needs_review"] is True


def test_worker_inventory_request_approval_has_consistent_audit(db):
    warehouse = Warehouse(name="Receiving warehouse", location="Test")
    db.add(warehouse)
    db.flush()
    worker = User(username="receiving-worker", full_name="Worker", role="warehouse_worker", password_hash="x", warehouse_id=warehouse.warehouse_id)
    manager = User(username="receiving-manager", full_name="Manager", role="manager", password_hash="x", warehouse_id=warehouse.warehouse_id)
    db.add_all([worker, manager])
    db.commit()

    def actor(user):
        return {"user_id": user.user_id, "username": user.full_name, "role": user.role, "warehouse_id": warehouse.warehouse_id}

    request = InventoryAdditionRequestCreate(product_name="Beans", quantity=12, category="Canned", unit_price=2)
    created = request_inventory_addition(request, db, actor(worker))
    approval = InventoryReceiptDetails(
        serial_number="BEANS-SERIAL-1",
        batch_number="BEANS-1",
        manufacturing_date=date.today() - timedelta(days=1),
        expiry_date=date.today() + timedelta(days=100),
        storage_zone="AMBIENT",
        temperature_c=20,
        aisle="A1",
        shelf_number="S1",
    )
    approved = approve_inventory_addition(created["request_id"], db, actor(manager))
    assert db.query(Inventory).count() == 0
    with pytest.raises(HTTPException) as early_error:
        receive_inventory_addition(created["request_id"] + 99, approval, db, actor(worker))
    assert early_error.value.status_code == 404
    result = receive_inventory_addition(created["request_id"], approval, db, actor(worker))
    addition = db.query(InventoryAdditionRequest).filter_by(request_id=created["request_id"]).one()
    inventory = db.query(Inventory).filter_by(warehouse_id=warehouse.warehouse_id).one()
    batch = db.query(Batch).filter_by(batch_id=inventory.batch_id).one()
    product = db.query(Product).filter_by(product_id=inventory.product_id).one()
    actions = {entry.action for entry in db.query(ActivityLog).all()}

    assert approved["status"] == "approved"
    assert result["status"] == "received"
    assert addition.status == "received"
    assert inventory.quantity == 12
    assert inventory.putaway_status == "confirmed"
    assert inventory.location_code == "A1-S1"
    assert batch.serial_number == "BEANS-SERIAL-1"
    assert product.serial_number == "BEANS-SERIAL-1"
    assert inventory.storage_zone == "AMBIENT"
    assert "INVENTORY_REQUEST_APPROVED" in actions
    assert "INVENTORY_RECEIVED" in actions
    assert "INVENTORY_REQUEST_REJECTED" not in actions

    reorder = request_inventory_addition(InventoryAdditionRequestCreate(product_name="Beans", quantity=6, category="Canned", unit_price=2), db, actor(worker))
    approve_inventory_addition(reorder["request_id"], db, actor(manager))
    second_receipt = approval.model_copy(update={"serial_number": "BEANS-SERIAL-2", "batch_number": "BEANS-2"})
    receive_inventory_addition(reorder["request_id"], second_receipt, db, actor(worker))
    second_batch = db.query(Batch).filter_by(batch_number="BEANS-2").one()
    assert second_batch.serial_number == "BEANS-SERIAL-2"
    assert product.serial_number == "BEANS-SERIAL-1"

    other = request_inventory_addition(InventoryAdditionRequestCreate(product_name="Rice", quantity=3, category="Dry", unit_price=1), db, actor(worker))
    approve_inventory_addition(other["request_id"], db, actor(manager))
    with pytest.raises(HTTPException) as serial_error:
        receive_inventory_addition(other["request_id"], approval.model_copy(update={"serial_number": "BEANS-SERIAL-2", "batch_number": "RICE-1"}), db, actor(worker))
    assert serial_error.value.status_code == 409

    legacy_duplicate = request_inventory_addition(InventoryAdditionRequestCreate(product_name="Flour", quantity=2, category="Dry", unit_price=1), db, actor(worker))
    approve_inventory_addition(legacy_duplicate["request_id"], db, actor(manager))
    with pytest.raises(HTTPException) as product_serial_error:
        receive_inventory_addition(legacy_duplicate["request_id"], approval.model_copy(update={"batch_number": "FLOUR-1"}), db, actor(worker))
    assert product_serial_error.value.status_code == 409

    rejected = request_inventory_addition(InventoryAdditionRequestCreate(product_name="Salt", quantity=1, category="Dry", unit_price=1), db, actor(worker))
    reject_inventory_addition(rejected["request_id"], db, actor(manager))
    assert db.query(InventoryAdditionRequest).filter_by(request_id=rejected["request_id"]).one().status == "rejected"


def test_inventory_receipt_rejects_blank_required_details():
    with pytest.raises(ValueError):
        InventoryReceiptDetails(
            serial_number="   ",
            batch_number="BATCH-1",
            manufacturing_date=date.today() - timedelta(days=1),
            expiry_date=date.today() + timedelta(days=1),
            aisle="A1",
            shelf_number="S1",
        )


def test_counter_checkout_rejects_multiple_lines_that_overdraw_same_stock(db):
    warehouse = Warehouse(name="Counter warehouse", location="Test")
    worker = User(username="counter-worker", full_name="Worker", role="warehouse_worker", password_hash="x")
    product = Product(name="Counter product", category="General", quantity=0, unit="units", price=3, units_per_box=1)
    db.add_all([warehouse, worker, product])
    db.flush()
    worker.warehouse_id = warehouse.warehouse_id
    batch = Batch(product_id=product.product_id, serial_number="COUNTER-SERIAL", batch_number="COUNTER-1", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=10))
    db.add(batch)
    db.flush()
    inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=10)
    db.add(inventory)
    db.flush()
    counter = CounterInventory(warehouse_id=warehouse.warehouse_id, product_id=product.product_id, batch_id=batch.batch_id, quantity=5, minimum_level=1, unit_price=product.price)
    db.add(counter)
    db.commit()

    request = CheckoutCreate(items=[
        CheckoutItem(scanned_code="COUNTER-SERIAL", quantity=3),
        CheckoutItem(scanned_code="COUNTER-SERIAL", quantity=3),
    ])
    actor = {"user_id": worker.user_id, "username": worker.full_name, "role": worker.role, "warehouse_id": warehouse.warehouse_id}
    with pytest.raises(HTTPException) as error:
        checkout(request, db, actor)

    assert error.value.status_code == 400
    assert counter.quantity == 5
    assert db.query(CounterSale).count() == 0


def test_counter_checkout_retry_with_same_key_records_one_sale_and_box_deduction(db):
    warehouse = Warehouse(name="Retry counter warehouse", location="Test")
    worker = User(username="retry-counter-worker", full_name="Worker", role="warehouse_worker", password_hash="x")
    product = Product(name="Retry counter product", category="General", quantity=0, unit="units", price=3, units_per_box=1)
    db.add_all([warehouse, worker, product])
    db.flush()
    worker.warehouse_id = warehouse.warehouse_id
    batch = Batch(product_id=product.product_id, serial_number="RETRY-COUNTER-CODE", batch_number="RETRY-COUNTER-1", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=10))
    db.add(batch)
    db.flush()
    inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=1)
    db.add(inventory)
    db.flush()
    counter = CounterInventory(warehouse_id=warehouse.warehouse_id, product_id=product.product_id, batch_id=batch.batch_id, quantity=1, minimum_level=1, unit_price=product.price)
    db.add(counter)
    db.commit()
    request = CheckoutCreate(request_key="RETRY-COUNTER-REQUEST", items=[CheckoutItem(scanned_code="RETRY-COUNTER-CODE", quantity=1)])
    actor = {"user_id": worker.user_id, "username": worker.full_name, "role": worker.role, "warehouse_id": warehouse.warehouse_id}

    first = checkout(request, db, actor)
    retry = checkout(request, db, actor)

    assert first["duplicate"] is False
    assert retry["duplicate"] is True
    assert retry["sale_id"] == first["sale_id"]
    assert first["items"][0]["serial_number"] == "RETRY-COUNTER-CODE"
    assert first["total_amount"] == 3
    assert counter.quantity == 0
    assert db.query(CounterSale).count() == 1
    assert db.query(CounterSaleItem).count() == 1


def test_manager_cannot_cancel_orders_or_reject_allocations_from_another_warehouse(db):
    first_warehouse = Warehouse(name="Scoped warehouse one", location="Test")
    second_warehouse = Warehouse(name="Scoped warehouse two", location="Test")
    first_manager = User(username="scope-manager-one", full_name="Manager One", role="manager", password_hash="x")
    second_manager = User(username="scope-manager-two", full_name="Manager Two", role="manager", password_hash="x")
    worker = User(username="scope-worker", full_name="Worker", role="warehouse_worker", password_hash="x")
    customer = Customer(name="Scoped buyer", phone="000")
    product = Product(name="Scoped product", category="General", quantity=0, unit="units", price=1, units_per_box=1)
    db.add_all([first_warehouse, second_warehouse, first_manager, second_manager, worker, customer, product])
    db.flush()
    first_manager.warehouse_id = first_warehouse.warehouse_id
    second_manager.warehouse_id = worker.warehouse_id = second_warehouse.warehouse_id
    batch = Batch(product_id=product.product_id, batch_number="SCOPED-1", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=10))
    db.add(batch)
    db.flush()
    inventory = Inventory(product_id=product.product_id, warehouse_id=second_warehouse.warehouse_id, batch_id=batch.batch_id, quantity=2)
    order = SalesOrder(customer_id=customer.customer_id, created_by=second_manager.user_id, warehouse_id=second_warehouse.warehouse_id, status="approved", reservation_status="reserved")
    db.add_all([inventory, order])
    db.flush()
    reservation = OrderInventoryReservation(order_id=order.order_id, inventory_id=inventory.inventory_id, product_id=product.product_id, batch_id=batch.batch_id, warehouse_id=second_warehouse.warehouse_id, quantity=2)
    db.add(reservation)
    db.commit()
    actor = {"user_id": first_manager.user_id, "username": first_manager.full_name, "role": first_manager.role, "warehouse_id": first_warehouse.warehouse_id}

    with pytest.raises(HTTPException) as cancel_error:
        cancel_order(order.order_id, db, actor)

    assert cancel_error.value.status_code == 404
    assert order.status == "approved"


def test_receiving_purchase_order_accepts_distinct_lots_per_product(db):
    warehouse = Warehouse(name="Multi-lot receiving warehouse", location="Test")
    manager = User(username="multi-lot-manager", full_name="Manager", role="manager", password_hash="x")
    worker = User(username="multi-lot-worker", full_name="Worker", role="warehouse_worker", password_hash="x")
    supplier = Supplier(name="Multi-lot supplier", phone="000")
    first_product = Product(name="Ambient rice", category="Dry goods", quantity=0, unit="units", price=2, units_per_box=1)
    second_product = Product(name="Chilled milk", category="Dairy", quantity=0, unit="units", price=3, units_per_box=1)
    db.add_all([warehouse, manager, worker, supplier, first_product, second_product])
    db.flush()
    manager.warehouse_id = worker.warehouse_id = warehouse.warehouse_id
    purchase_order = PurchaseOrder(supplier_id=supplier.supplier_id, created_by=manager.user_id, warehouse_id=warehouse.warehouse_id, status="pending")
    db.add(purchase_order)
    db.flush()
    db.add_all([
        PurchaseOrderItem(purchase_order_id=purchase_order.purchase_order_id, product_id=first_product.product_id, quantity=10, unit_price=first_product.price),
        PurchaseOrderItem(purchase_order_id=purchase_order.purchase_order_id, product_id=second_product.product_id, quantity=6, unit_price=second_product.price),
    ])
    db.commit()
    receiving = ReceivePurchaseOrder(warehouse_id=warehouse.warehouse_id, items=[
        ReceiveItem(product_id=first_product.product_id, serial_number="RICE-SERIAL", quantity=10, batch_number="RICE-LOT-A", manufacturing_date=date.today() - timedelta(days=2), expiry_date=date.today() + timedelta(days=100), storage_zone="AMBIENT", temperature_c=20),
        ReceiveItem(product_id=second_product.product_id, serial_number="MILK-SERIAL", quantity=6, batch_number="MILK-LOT-B", manufacturing_date=date.today() - timedelta(days=1), expiry_date=date.today() + timedelta(days=20), storage_zone="CHILLED", temperature_c=4),
    ])
    actor = {"user_id": worker.user_id, "username": worker.full_name, "role": worker.role, "warehouse_id": warehouse.warehouse_id}

    response = receive_purchase_order(purchase_order.purchase_order_id, receiving, db, actor)

    assert response["status"] == "received"
    assert response["quarantined_batches"] == []
    records = db.query(Inventory).filter_by(warehouse_id=warehouse.warehouse_id).all()
    assert {(record.product_id, record.quantity, record.storage_zone, record.putaway_status) for record in records} == {
        (first_product.product_id, 10, "AMBIENT", "pending"),
        (second_product.product_id, 6, "CHILLED", "pending"),
    }
    assert {batch.batch_number for batch in db.query(Batch).all()} == {"RICE-LOT-A", "MILK-LOT-B"}

    duplicate_order = PurchaseOrder(supplier_id=supplier.supplier_id, created_by=manager.user_id, warehouse_id=warehouse.warehouse_id, status="pending")
    db.add(duplicate_order)
    db.flush()
    db.add(PurchaseOrderItem(purchase_order_id=duplicate_order.purchase_order_id, product_id=first_product.product_id, quantity=1, unit_price=first_product.price))
    db.commit()
    duplicate_receiving = ReceivePurchaseOrder(warehouse_id=warehouse.warehouse_id, items=[
        ReceiveItem(product_id=first_product.product_id, serial_number="RICE-SERIAL", quantity=1, batch_number="RICE-LOT-A", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=100), storage_zone="AMBIENT", temperature_c=20),
    ])
    with pytest.raises(HTTPException) as duplicate_error:
        receive_purchase_order(duplicate_order.purchase_order_id, duplicate_receiving, db, actor)
    assert duplicate_error.value.status_code == 409
    assert duplicate_order.status == "pending"
    
def test_manager_can_cancel_pending_purchase_order(db):
    warehouse = Warehouse(name="Cancel PO warehouse", location="Test")
    manager = User(username="cancel-po-manager", full_name="Manager", role="manager", password_hash="x")
    supplier = Supplier(name="Cancel PO supplier", phone="000")
    product = Product(name="Cancel PO product", category="General", quantity=0, unit="units", price=1, units_per_box=1)
    db.add_all([warehouse, manager, supplier, product])
    db.flush()
    manager.warehouse_id = warehouse.warehouse_id
    order = PurchaseOrder(supplier_id=supplier.supplier_id, created_by=manager.user_id, warehouse_id=warehouse.warehouse_id, status="pending")
    db.add(order)
    db.flush()
    db.add(PurchaseOrderItem(purchase_order_id=order.purchase_order_id, product_id=product.product_id, quantity=5, unit_price=product.price))
    db.commit()
    actor = {"user_id": manager.user_id, "username": manager.full_name, "role": manager.role, "warehouse_id": warehouse.warehouse_id}

    result = cancel_purchase_order(order.purchase_order_id, db, actor)

    assert result["status"] == "cancelled"
    assert order.status == "cancelled"


def test_transfer_queue_is_scoped_to_manager_warehouse(db):
    source = Warehouse(name="Source", location="Test")
    destination = Warehouse(name="Destination", location="Test")
    unrelated = Warehouse(name="Unrelated", location="Test")
    db.add_all([source, destination, unrelated])
    db.flush()
    manager = User(username="transfer-manager", full_name="Manager", role="manager", password_hash="x", warehouse_id=source.warehouse_id)
    worker = User(username="transfer-worker", full_name="Worker", role="warehouse_worker", password_hash="x", warehouse_id=source.warehouse_id)
    other_worker = User(username="other-transfer-worker", full_name="Other worker", role="warehouse_worker", password_hash="x", warehouse_id=unrelated.warehouse_id)
    product = Product(name="Transfer product", category="General", quantity=0, unit="units", price=1, units_per_box=1)
    db.add_all([manager, worker, other_worker, product])
    db.flush()
    batch = Batch(product_id=product.product_id, batch_number="TRANSFER-1", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=10))
    db.add(batch)
    db.flush()
    owned_request = StockTransfer(product_id=product.product_id, batch_id=batch.batch_id, source_warehouse_id=source.warehouse_id, destination_warehouse_id=destination.warehouse_id, quantity=2, created_by=worker.user_id)
    incoming_request = StockTransfer(product_id=product.product_id, batch_id=batch.batch_id, source_warehouse_id=unrelated.warehouse_id, destination_warehouse_id=source.warehouse_id, quantity=1, created_by=other_worker.user_id)
    unrelated_request = StockTransfer(product_id=product.product_id, batch_id=batch.batch_id, source_warehouse_id=destination.warehouse_id, destination_warehouse_id=unrelated.warehouse_id, quantity=1, created_by=other_worker.user_id)
    db.add_all([owned_request, incoming_request, unrelated_request])
    db.commit()

    manager_rows = list_stock_transfers(db, {"user_id": manager.user_id, "role": "manager", "warehouse_id": source.warehouse_id})["transfers"]

    assert {row["transfer_id"] for row in manager_rows} == {owned_request.transfer_id, incoming_request.transfer_id}


def test_local_expiry_job_contains_database_failures(monkeypatch):
    class FakeSession:
        rolled_back = False
        closed = False

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    session = FakeSession()

    def fail_processing(_db):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main_module, "SessionLocal", lambda: session)
    monkeypatch.setattr(main_module, "process_expiry", fail_processing)

    main_module.run_expiry_job()

    assert session.rolled_back
    assert session.closed


def test_local_inventory_job_contains_database_failures(monkeypatch):
    class FakeSession:
        rolled_back = False
        closed = False

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    session = FakeSession()

    def fail_processing(_db):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main_module, "SessionLocal", lambda: session)
    monkeypatch.setattr(main_module, "process_inventory_intelligence", fail_processing)

    main_module.run_inventory_intelligence_job()

    assert session.rolled_back
    assert session.closed


def test_expiry_is_idempotent_and_deduplicates_notifications(db):
    _, _, batch, inventory = seed_expiring_inventory(db)
    first = process_expiry(db, date.today())
    second = process_expiry(db, date.today())
    db.refresh(inventory)
    db.refresh(batch)
    assert first["expired_units"] == 100
    assert second["expired_units"] == 0
    assert inventory.quantity == 0
    assert inventory.expired_quantity == 100
    assert batch.status == "expired"
    assert db.query(InventoryMovement).filter(InventoryMovement.movement_type == "EXPIRED").count() == 1
    assert db.query(Notification).count() == 2


def test_active_batch_is_untouched_and_warning_is_created(db):
    warehouse = Warehouse(name="Warning warehouse", location="Test")
    worker = User(username="warning-worker", full_name="Worker", role="warehouse_worker", password_hash="x")
    product = Product(name="Yogurt", category="Dairy", quantity=0, unit="units", price=1, units_per_box=1)
    db.add_all([warehouse, worker, product])
    db.flush()
    worker.warehouse_id = warehouse.warehouse_id
    batch = Batch(product_id=product.product_id, batch_number="WARN-7", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=7))
    active_batch = Batch(product_id=product.product_id, batch_number="ACTIVE-8", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=8))
    db.add_all([batch, active_batch])
    db.flush()
    active_inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=active_batch.batch_id, quantity=20)
    warning_inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=30)
    db.add_all([active_inventory, warning_inventory])
    db.commit()
    result = process_expiry(db, date.today())
    db.refresh(active_inventory)
    assert active_inventory.quantity == 20
    assert result["expired_units"] == 0
    assert db.query(Notification).filter(Notification.notification_type == "inventory_expiry_warning").count() == 1


def test_intelligence_creates_actionable_recommendations(db, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "")
    monkeypatch.setenv("AI_MODEL", "")
    warehouse, product, batch, inventory = seed_expiring_inventory(db)
    inventory.quantity = 10
    batch.expiry_date = date.today() + timedelta(days=1)
    customer = Customer(name="Test customer", phone="000")
    db.add(customer)
    db.flush()
    order = SalesOrder(customer_id=customer.customer_id, created_by=1, warehouse_id=warehouse.warehouse_id, status="confirmed")
    db.add(order)
    db.flush()
    db.add(SalesOrderItem(order_id=order.order_id, product_id=product.product_id, quantity=150, unit_price=product.price))
    db.commit()
    result = process_inventory_intelligence(db)
    assert isinstance(result["evaluated"], int)
    assert result["notifications"] > 0
    assert db.query(InventoryRecommendation).count() == 1
    notification_count = db.query(Notification).count()
    process_inventory_intelligence(db)
    assert db.query(Notification).count() == notification_count


def test_ai_inventory_suggestions_reject_unknown_and_ineligible_products(monkeypatch):
    monkeypatch.setattr(ai_assistant, "complete", lambda *_args, **_kwargs: '{"suggestions":['
        '{"product_id":1,"action":"ORDER_REVIEW","priority":"HIGH"},'
        '{"product_id":2,"action":"ORDER_REVIEW","priority":"HIGH"},'
        '{"product_id":999,"action":"INVENTORY_CHECK","priority":"HIGH"}]}')
    suggestions = suggest_inventory_actions([
        {"product_id": 1, "product_name": "Rice", "current_stock": 2, "recommended_reorder": 8, "stockout_risk": "HIGH", "waste_risk": "LOW", "estimated_days_remaining": 2},
        {"product_id": 2, "product_name": "Beans", "current_stock": 50, "recommended_reorder": 0, "stockout_risk": "LOW", "waste_risk": "LOW", "estimated_days_remaining": None},
    ])
    assert suggestions == [{"product_id": 1, "action": "ORDER_REVIEW", "priority": "HIGH"}]


def test_ai_inventory_suggestions_parse_json_embedded_in_provider_text(monkeypatch):
    monkeypatch.setattr(ai_assistant, "complete", lambda *_args, **_kwargs: (
        'Here are the suggestions:\n```json\n'
        '{"suggestions":[{"product_id":1,"action":"ORDER_REVIEW","priority":"HIGH"}]}\n'
        '```'
    ))
    suggestions = suggest_inventory_actions([
        {"product_id": 1, "product_name": "Rice", "current_stock": 2, "recommended_reorder": 8, "stockout_risk": "HIGH", "waste_risk": "LOW", "estimated_days_remaining": 2},
    ])
    assert suggestions == [{"product_id": 1, "action": "ORDER_REVIEW", "priority": "HIGH"}]


def test_ai_inventory_suggestions_ignore_invalid_provider_json(monkeypatch):
    monkeypatch.setattr(ai_assistant, "complete", lambda *_args, **_kwargs: "not JSON")
    suggestions = suggest_inventory_actions([
        {"product_id": 1, "product_name": "Rice", "current_stock": 2, "recommended_reorder": 8, "stockout_risk": "HIGH", "waste_risk": "LOW", "estimated_days_remaining": 2},
    ])
    assert suggestions == []


def test_ai_inventory_notifications_are_deduplicated_and_role_scoped(db, monkeypatch):
    warehouse = Warehouse(name="AI warehouse", location="Test")
    db.add(warehouse)
    db.flush()
    manager = User(username="ai-manager", full_name="Manager", role="manager", password_hash="x", warehouse_id=warehouse.warehouse_id)
    worker = User(username="ai-worker", full_name="Worker", role="warehouse_worker", password_hash="x", warehouse_id=warehouse.warehouse_id)
    product = Product(name="AI rice", category="Dry goods", quantity=0, unit="kg", price=2, units_per_box=1, reorder_level=10)
    db.add_all([manager, worker, product])
    db.flush()
    batch = Batch(product_id=product.product_id, batch_number="AI-1", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=30))
    db.add(batch)
    db.flush()
    db.add(Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=2))
    db.commit()
    suggestion = {"product_id": product.product_id, "action": "ORDER_REVIEW", "priority": "HIGH"}
    monkeypatch.setattr(intelligence_module, "suggest_inventory_actions", lambda _results: [suggestion])

    process_inventory_intelligence(db)
    process_inventory_intelligence(db)

    notifications = db.query(Notification).filter(Notification.notification_type == "ai_inventory_suggestion").all()
    assert len(notifications) == 1
    assert notifications[0].user_id == manager.user_id


def test_expired_batch_is_rejected_by_shared_inventory_guard(db):
    _, _, batch, _ = seed_expiring_inventory(db)
    with pytest.raises(HTTPException) as error:
        require_available_batch(db, batch.batch_id)
    assert error.value.status_code == 400


def test_fefo_plan_skips_expired_batches(db):
    warehouse, product, batch, _ = seed_expiring_inventory(db)
    assert _fefo_plan(db, product.product_id, warehouse.warehouse_id, 1) == []


def test_batches_expiring_today_are_not_saleable(db):
    warehouse = Warehouse(name="Expiry-day warehouse", location="Test")
    product = Product(name="Yogurt", category="Dairy", quantity=0, unit="units", price=2, units_per_box=1)
    db.add_all([warehouse, product])
    db.flush()
    batch = Batch(
        product_id=product.product_id,
        batch_number="EXPIRES-TODAY",
        manufacturing_date=date.today() - timedelta(days=1),
        expiry_date=date.today(),
    )
    db.add(batch)
    db.flush()
    db.add(Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=5))
    db.commit()

    with pytest.raises(HTTPException) as error:
        require_available_batch(db, batch.batch_id)
    assert error.value.status_code == 400
    assert _fefo_plan(db, product.product_id, warehouse.warehouse_id, 1) == []


def test_fefo_plan_allocates_across_valid_batches(db):
    warehouse = Warehouse(name="FEFO warehouse", location="Test")
    product = Product(name="Rice", category="Boxed items", quantity=0, unit="kg", price=2, units_per_box=1)
    db.add_all([warehouse, product])
    db.flush()
    first = Batch(product_id=product.product_id, batch_number="FEFO-A", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=2))
    second = Batch(product_id=product.product_id, batch_number="FEFO-B", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=10))
    db.add_all([first, second])
    db.flush()
    db.add_all([Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=first.batch_id, quantity=100), Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=second.batch_id, quantity=300)])
    db.commit()
    plan = _fefo_plan(db, product.product_id, warehouse.warehouse_id, 120)
    assert [(item["batch_number"], item["quantity"]) for item in plan] == [("FEFO-A", 100), ("FEFO-B", 20)]


def test_internal_job_secret_rejects_unauthorized_requests(monkeypatch):
    monkeypatch.setenv("INTERNAL_JOB_SECRET", "test-secret")
    with pytest.raises(HTTPException) as error:
        require_job_secret("wrong-secret")
    assert error.value.status_code == 401


def test_internal_expiry_job_requires_secret(monkeypatch):
    monkeypatch.setenv("INTERNAL_JOB_SECRET", "test-secret")
    with pytest.raises(HTTPException):
        process_expiry_job(None)


def test_internal_expiry_job_authorized_request_is_safe(monkeypatch, db):
    monkeypatch.setenv("INTERNAL_JOB_SECRET", "test-secret")
    monkeypatch.setattr(internal_jobs, "SessionLocal", lambda: db)
    monkeypatch.setattr(internal_jobs, "process_expiry", lambda _db: {"expired_batches": 0, "expired_units": 0, "warnings": 0})
    response = process_expiry_job("test-secret")
    assert response["status"] == "ok"

def test_store_order_flow_moves_a_serial_batch_from_warehouse_to_counter(db):
    from app.models.store_order import StoreOrder
    from app.routers.store_orders import create_store_order, dispatch_store_order, list_available_batches, receive_store_order
    from app.schemas.store_order import StoreOrderCreate

    warehouse, product, batch, inventory = seed_expiring_inventory(db)
    batch.expiry_date = date.today() + timedelta(days=30)
    batch.serial_number = "MILK-SERIAL-9"
    inventory.putaway_status = "confirmed"
    db.commit()
    manager = db.query(User).filter_by(role="manager").one()
    worker = db.query(User).filter_by(role="warehouse_worker").one()

    def actor(user):
        return {"user_id": user.user_id, "username": user.full_name, "role": user.role, "warehouse_id": warehouse.warehouse_id}

    available = list_available_batches(db, actor(manager))["items"]
    assert available[0]["serial_number"] == "MILK-SERIAL-9" and available[0]["available_quantity"] == 100
    with pytest.raises(HTTPException) as too_many:
        create_store_order(StoreOrderCreate(inventory_id=inventory.inventory_id, quantity=101, needed_by=datetime.utcnow() + timedelta(hours=4)), db, actor(manager))
    assert too_many.value.status_code == 400
    created = create_store_order(StoreOrderCreate(inventory_id=inventory.inventory_id, quantity=40, needed_by=datetime.utcnow() + timedelta(hours=4)), db, actor(manager))
    assert list_available_batches(db, actor(manager))["items"][0]["available_quantity"] == 60
    with pytest.raises(HTTPException):
        receive_store_order(created["store_order_id"], db, actor(manager))
    dispatch_store_order(created["store_order_id"], db, actor(worker))
    assert inventory.quantity == 60
    receive_store_order(created["store_order_id"], db, actor(manager))

    counter = db.query(CounterInventory).one()
    assert counter.quantity == 40 and counter.batch_id == batch.batch_id
    assert db.query(StoreOrder).one().status == "received"
    looked_up = lookup_counter_barcode("MILK-SERIAL-9", db, actor(manager))
    assert looked_up["available_quantity"] == 40 and looked_up["product_name"] == "Milk"


def test_cashier_checkout_splits_across_batches_and_creates_cashier_account(db):
    from app.routers.cashiers import create_cashier, cashier_login, list_cashiers
    from app.routers.counter import get_counter_sales
    from app.schemas.store_order import CashierCreate, CashierLogin

    warehouse, product, batch, inventory = seed_expiring_inventory(db)
    batch.expiry_date = date.today() + timedelta(days=3)
    batch.serial_number = "SPLIT-SERIAL"
    later = Batch(product_id=product.product_id, serial_number="SPLIT-SERIAL", batch_number="SPLIT-2", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=9))
    db.add(later)
    db.flush()
    db.add_all([
        CounterInventory(warehouse_id=warehouse.warehouse_id, product_id=product.product_id, batch_id=batch.batch_id, quantity=2, minimum_level=0, unit_price=2),
        CounterInventory(warehouse_id=warehouse.warehouse_id, product_id=product.product_id, batch_id=later.batch_id, quantity=5, minimum_level=0, unit_price=2),
    ])
    db.commit()
    manager = db.query(User).filter_by(role="manager").one()
    manager_actor = {"user_id": manager.user_id, "username": manager.full_name, "role": manager.role, "warehouse_id": warehouse.warehouse_id}

    created = create_cashier(CashierCreate(full_name="Till One"), db, manager_actor)
    assert len(created["cashier_id"]) == 10 and created["cashier_id"].isdigit()
    assert list_cashiers(db, manager_actor)["cashiers"][0]["cashier_id"] == created["cashier_id"]
    with pytest.raises(HTTPException) as duplicate:
        create_cashier(CashierCreate(full_name="Dup", cashier_id=created["cashier_id"]), db, manager_actor)
    assert duplicate.value.status_code == 409

    class FakeRequest:
        client = type("Client", (), {"host": "test-host"})()

    assert cashier_login(CashierLogin(cashier_id=created["cashier_id"]), FakeRequest(), db)["access_token"]
    with pytest.raises(HTTPException) as bad_login:
        cashier_login(CashierLogin(cashier_id="0000000000"), FakeRequest(), db)
    assert bad_login.value.status_code == 401

    cashier = db.query(User).filter_by(username=created["cashier_id"]).one()
    cashier_actor = {"user_id": cashier.user_id, "username": cashier.full_name, "role": cashier.role, "warehouse_id": warehouse.warehouse_id}
    sale = checkout(CheckoutCreate(items=[CheckoutItem(scanned_code="SPLIT-SERIAL", quantity=4)]), db, cashier_actor)

    assert sale["total_amount"] == 8
    assert sale["items"][0]["quantity"] == 4 and sale["cashier_name"] == "Till One"
    assert sorted(row.quantity for row in db.query(CounterInventory).all()) == [0, 3]
    assert db.query(CounterSaleItem).count() == 2
    assert get_counter_sales(db, manager_actor)["sales"][0]["bill_number"] == sale["bill_number"]
    with pytest.raises(HTTPException) as unknown:
        checkout(CheckoutCreate(items=[CheckoutItem(scanned_code="NOPE", quantity=1)]), db, cashier_actor)
    assert unknown.value.status_code == 404


def test_worker_can_delete_own_account_and_email_is_freed(db):
    from app.routers.users import remove_own_worker_account
    from app.schemas.user import UserDelete

    warehouse, *_ = seed_expiring_inventory(db)
    worker = db.query(User).filter_by(role="warehouse_worker").one()
    worker.email = "w@example.com"
    worker.password_hash = hash_password("secret-pass")
    db.add(RegistrationRequest(username="w", full_name="Worker", email="w@example.com", role="warehouse_worker", password_hash="x", warehouse_id=warehouse.warehouse_id, status="approved"))
    db.commit()
    actor = {"user_id": worker.user_id, "username": worker.full_name, "role": worker.role, "warehouse_id": warehouse.warehouse_id}

    with pytest.raises(HTTPException) as wrong:
        remove_own_worker_account(UserDelete(password="nope"), db, actor)
    assert wrong.value.status_code == 401
    remove_own_worker_account(UserDelete(password="secret-pass"), db, actor)

    assert db.query(User).filter_by(email="w@example.com").count() == 0
    assert db.query(RegistrationRequest).filter_by(email="w@example.com").count() == 0


def test_each_warehouse_only_sees_its_own_products_and_serials(db):
    from app.routers.products import get_products
    from app.routers.customers import get_customers

    first = Warehouse(name="North", location="N")
    second = Warehouse(name="South", location="S")
    db.add_all([first, second])
    db.flush()
    milk_north = Product(name="Milk", warehouse_id=first.warehouse_id, category="Dairy", quantity=0, unit="units", price=1, serial_number="SAME-SERIAL")
    milk_south = Product(name="Milk", warehouse_id=second.warehouse_id, category="Dairy", quantity=0, unit="units", price=1, serial_number="SAME-SERIAL")
    db.add_all([milk_north, milk_south, Customer(name="North buyer", phone="1", warehouse_id=first.warehouse_id)])
    db.commit()

    north = {"user_id": 1, "role": "manager", "warehouse_id": first.warehouse_id}
    south = {"user_id": 2, "role": "manager", "warehouse_id": second.warehouse_id}
    assert [p.product_id for p in get_products(db, north)["products"]] == [milk_north.product_id]
    assert [p.product_id for p in get_products(db, south)["products"]] == [milk_south.product_id]
    assert get_customers(db, south)["customers"] == []
