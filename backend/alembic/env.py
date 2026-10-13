from logging.config import fileConfig
import os

from dotenv import load_dotenv

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.database import Base
from app.models.batch import Batch
from app.models.inventory import Inventory
from app.models.inventory_movement import InventoryMovement
from app.models.notification import Notification
from app.models.inventory_recommendation import InventoryRecommendation
from app.models.counter_inventory import CounterInventory
from app.models.counter_allocation import CounterAllocation
from app.models.counter_sale import CounterSale, CounterSaleItem
from app.models.order_inventory_reservation import OrderInventoryReservation

config = context.config
load_dotenv()
if os.getenv("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
