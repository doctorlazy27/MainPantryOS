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
        "update_inventory",
        "manage_users",
        "manage_warehouses",
        "send_messages",
        "approve_sales_orders",
        "create_orders",
        "request_warehouse_stock",
        "confirm_order_receipt",
        "send_invoices",
        "request_stock_transfer",
        "approve_stock_transfers",
        "view_stock_transfers",
        "view_invoices",
        "confirm_invoices",
        "approve_inventory_requests",
        "view_inventory_recommendations",
        "review_inventory_recommendations",
        "create_purchase_orders",
        "view_counter_inventory",
        "view_counter_sales",
        "request_counter_allocation",
        "approve_counter_allocation",
        "checkout_counter",
    },

    UserRole.WAREHOUSE_WORKER: {
    "view_warehouses",
    "view_orders",
    "view_activity",
    "view_inventory",
    "view_ai_copilot",
    "update_inventory",
    "pick_stock",
    "process_stock_requests",
    "fulfill_orders",
    "receive_purchase_orders",
    "send_messages",
    "submit_inventory_requests",
    "checkout_counter",
},

}


def has_permission(role: UserRole, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())