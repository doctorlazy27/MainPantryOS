from app.auth.roles import UserRole


PERMISSIONS = {
    UserRole.MANAGER: {
        "view_customers",
        "view_suppliers",
        "view_warehouses",
        "view_orders",
        "view_inventory",
        "view_ai_copilot",
        "view_activity",
        "manage_users",
        "manage_cashiers",
        "manage_warehouses",
        "send_messages",
        "approve_sales_orders",
        "create_orders",
        "confirm_order_receipt",
        "send_invoices",
        "request_stock_transfer",
        "approve_stock_transfers",
        "view_stock_transfers",
        "view_invoices",
        "confirm_invoices",
        "approve_inventory_requests",
        "view_inventory_recommendations",
        "view_counter_inventory",
        "view_counter_sales",
        "view_store_orders",
        "request_store_orders",
        "receive_store_orders",
    },

    UserRole.WAREHOUSE_WORKER: {
    "view_warehouses",
    "view_orders",
    "view_activity",
    "view_inventory",
    "view_ai_copilot",
    "update_inventory",
    "pick_stock",
    "fulfill_orders",
    "receive_purchase_orders",
    "send_messages",
    "submit_inventory_requests",
    "view_store_orders",
    "dispatch_store_orders",
},

    UserRole.CASHIER: {
        "checkout_counter",
    },
}


def has_permission(role: UserRole, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())