"""Create the existing application schema for fresh databases.

Revision ID: 0000_initial_schema
Revises:
"""
from alembic import op

from app.database import Base
from app.models import activity_log, auth_session, batch, boxed_unit, customer, inventory, inventory_addition_request, inventory_movement, inventory_recommendation, invoice, message, notification, order, order_item, product, purchase_order, purchase_order_item, registration_request, salesperson_inventory, stock_transfer, supplier, user, warehouse, warehouse_request

revision = "0000_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
