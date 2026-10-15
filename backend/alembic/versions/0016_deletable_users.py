"""Let user rows be deleted directly (e.g. in pgAdmin) without foreign-key errors."""

from alembic import op
import sqlalchemy as sa


revision = "0016_deletable_users"
down_revision = "0015_warehouse_scoping"
branch_labels = None
depends_on = None

# Rows that only make sense for their owner go with them; everything else keeps its history with the user reference cleared.
_CASCADE_TABLES = {"auth_sessions", "notifications", "messages"}

_FOREIGN_KEYS = """
SELECT c.conname, c.conrelid::regclass::text AS tbl, a.attname AS col, a.attnotnull AS notnull
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
WHERE c.contype = 'f' AND array_length(c.conkey, 1) = 1 AND c.confrelid = '{target}'::regclass
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for name, table, column, not_null in bind.execute(sa.text(_FOREIGN_KEYS.format(target="users"))).all():
        table = table.replace('"', "").split(".")[-1]
        action = "CASCADE" if table in _CASCADE_TABLES else "SET NULL"
        op.drop_constraint(name, table, type_="foreignkey")
        if action == "SET NULL" and not_null:
            op.alter_column(table, column, existing_type=sa.Integer(), nullable=True)
        op.create_foreign_key(name, table, "users", [column], ["user_id"], ondelete=action)
    for name, table, column, _not_null in bind.execute(sa.text(_FOREIGN_KEYS.format(target="messages"))).all():
        if table.replace('"', "") != "messages":
            continue
        op.drop_constraint(name, "messages", type_="foreignkey")
        op.create_foreign_key(name, "messages", "messages", [column], ["message_id"], ondelete="SET NULL")


def downgrade() -> None:
    # Restoring the old RESTRICT behaviour would fail once rows hold NULL user references.
    pass
