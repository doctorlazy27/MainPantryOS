"""Persist manager-reviewable inventory recommendations.

Revision ID: 0002_inventory_recommendations
Revises: 0001_automation_hardening
"""
from alembic import op


revision = "0002_inventory_recommendations"
down_revision = "0001_automation_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE IF NOT EXISTS inventory_recommendations (recommendation_id SERIAL PRIMARY KEY, recommendation_key VARCHAR(180) NOT NULL UNIQUE, product_id INTEGER NOT NULL REFERENCES products(product_id), warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id), recommendation_type VARCHAR(40) NOT NULL, current_stock INTEGER NOT NULL, average_daily_demand DOUBLE PRECISION NOT NULL DEFAULT 0, recommended_quantity INTEGER NOT NULL DEFAULT 0, reason TEXT NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'PENDING', created_at TIMESTAMP NOT NULL DEFAULT NOW(), reviewed_by INTEGER REFERENCES users(user_id), reviewed_at TIMESTAMP)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS inventory_recommendations")