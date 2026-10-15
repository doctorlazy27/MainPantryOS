"""Batch numbers only need to be unique per product, so warehouses never collide."""

from alembic import op
import sqlalchemy as sa


revision = "0017_batch_number_scope"
down_revision = "0016_deletable_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints("batches"):
        if constraint["column_names"] == ["batch_number"]:
            op.drop_constraint(constraint["name"], "batches", type_="unique")
    for index in inspector.get_indexes("batches"):
        if index["column_names"] == ["batch_number"] and index.get("unique"):
            op.drop_index(index["name"], table_name="batches")
    op.create_unique_constraint("uq_batches_product_batch_number", "batches", ["product_id", "batch_number"])


def downgrade() -> None:
    op.drop_constraint("uq_batches_product_batch_number", "batches", type_="unique")
    op.create_unique_constraint("batches_batch_number_key", "batches", ["batch_number"])
