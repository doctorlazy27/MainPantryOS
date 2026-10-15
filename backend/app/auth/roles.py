from enum import Enum


class UserRole(str, Enum):
    MANAGER = "manager"
    WAREHOUSE_WORKER = "warehouse_worker"
    CASHIER = "cashier"
