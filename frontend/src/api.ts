export type Role = 'manager' | 'warehouse_worker' | 'cashier'
export type AuthUser = { user_id: number; username: string; role: Role; warehouse_id: number | null }
export type RegistrationRequest = { request_id: number; username: string; full_name: string; role: Role; status: string; requested_at: string }

export type DashboardData = {
  total_products: number
  total_inventory_records: number
  pending_sales_orders: number
  approved_sales_orders: number
  pending_purchase_orders: number
  unread_notifications: number
  low_stock_products: Array<{
    product_id: number
    name: string
    current_quantity: number
    reorder_level: number
    unit: string
  }>
  expiring_batches: Array<{
    product_name: string
    batch_number: string
    quantity: number
    expiry_date: string
  }>
  inventory_intelligence: Array<{
    product_id: number
    product_name: string
    current_stock: number
    average_daily_demand: number
    estimated_days_remaining: number | null
    stockout_risk: string
    waste_risk: string
    potential_surplus: number
    recommended_reorder: number
    recommendation: string
  }>
}

export type Product = { product_id: number; name: string; serial_number?: string | null; category: string; storage_section: string; shelf_number: string; aisle: string; quantity: number; unit: string; price: number; reorder_level: number; units_per_box: number }
export type InventoryRecord = { inventory_id: number; product_id: number; warehouse_id: number; batch_id: number; quantity: number; serial_number?: string | null; expiry_date?: string | null; boxed_units: number; units_per_box: number; unit_price: number; box_unit_cost: number; total_box_cost: number; boxed_unit_ids: string[]; storage_zone?: string; location_code?: string; putaway_status?: string; batch_status?: string; batch_number?: string }
export type Warehouse = { warehouse_id: number; name: string; location: string }
export type Customer = { customer_id: number; name: string; phone: string; email?: string; address?: string }
export type Supplier = { supplier_id: number; name: string; phone: string; email?: string; address?: string }
export type User = { user_id: number; username: string; full_name: string; role: Role; warehouse_id: number | null }
export type Notification = { notification_id: number; title: string; message: string; notification_type: string; is_read: boolean; created_at: string }
export type MessageContact = { user_id: number; username: string; full_name: string; role: Role }
export type IncomingMessage = { message_id: number; sender_id: number; sender_username: string; sender_role: Role; subject: string; body: string; is_read: boolean; created_at: string; reply_to_id?: number; can_reply: boolean }
export type Invoice = { invoice_id: number; order_id: number; customer_id: number; generated_by?: string; total_amount: number; status: string; created_at?: string; sent_at?: string; confirmed_at?: string }
export type InvoiceReportPeriod = 'weekly' | 'monthly' | 'yearly'
export type InvoiceReport = { period: InvoiceReportPeriod; starts_on: string; ends_on: string; invoice_count: number; total_amount: number; by_status: Record<string, { count: number; amount: number }>; previous_period: { invoice_count: number; total_amount: number }; change_percent: number | null }
export type CounterInventory = { counter_inventory_id: number; product_id: number; product_name: string; serial_number?: string | null; category: string; batch_id: number; batch_number: string; quantity: number; minimum_level: number; unit_price: number; expiry_date: string; status: string; last_replenished_at?: string }
export type CounterSaleLine = { product_id: number; product_name: string; serial_number: string | null; quantity: number; unit_price: number; line_total: number }
export type CounterSale = { sale_id: number; bill_number: string; total_amount: number; worker_id: number; cashier_name: string | null; created_at: string; items: CounterSaleLine[]; duplicate?: boolean }
export type InventoryRequest = { request_id: number; product_id: number; product_name: string; category: string; quantity: number; boxed_units: number; units_per_box: number; unit_price: number; batch_number?: string | null; serial_number?: string | null; status: 'pending' | 'approved' | 'received' | 'rejected'; requested_by: number; created_at: string; reviewed_at?: string | null; received_at?: string | null }
export type StoreOrder = { store_order_id: number; product_id: number; product_name: string; batch_id: number; batch_number: string; serial_number: string; quantity: number; needed_by: string; status: 'pending' | 'dispatched' | 'received' | 'rejected' | 'cancelled'; note?: string | null; created_at: string; dispatched_at?: string | null; received_at?: string | null }
export type AvailableBatch = { inventory_id: number; product_id: number; product_name: string; serial_number: string | null; batch_id: number; batch_number: string; expiry_date: string; available_quantity: number; counter_quantity: number; counter_minimum: number; counter_low: boolean }
export type Cashier = { user_id: number; full_name: string; cashier_id: string; sales_count: number }
export type PurchaseOrder = { purchase_order_id: number; supplier_name: string; warehouse_id: number | null; status: string; created_at: string; items: Array<{ product_id: number; product_name: string; quantity: number }> }
export type SalesOrder = { order_id: number; customer_id: number; created_by: number; status: string; reservation_status?: string; created_at: string; items: Array<{ product_id: number; product_name: string; quantity: number }>; pick_progress?: Record<number, number> }
export type PutawayTask = { inventory_id: number; product_name: string; batch_number: string; quantity: number; storage_zone: 'AMBIENT' | 'CHILLED' | 'FROZEN'; expiry_date: string }
export type TemperatureLog = { temperature_log_id: number; batch_id: number; inventory_id: number | null; stage: string; storage_zone: string; temperature_c: number; minimum_c: number; maximum_c: number | null; within_range: boolean; recorded_at: string }
export type StockTransfer = { transfer_id: number; product_id: number; product_name: string; batch_id: number; batch_number: string; source_warehouse_id: number; source_warehouse_name: string; destination_warehouse_id: number; destination_warehouse_name: string; quantity: number; status: string; created_at: string }
export type InventoryRecommendation = { recommendation_id: number; product_id: number; product_name: string; warehouse_id: number; recommendation_type: string; current_stock: number; average_daily_demand: number; recommended_quantity: number; reason: string; status: string; created_at: string }
export type OperationalMetrics = { period_days: number; sold_units: number; current_saleable_stock: number; stock_turn_rate: number | null; fefo_verified_units: number; fulfilled_units: number; fefo_compliance_percent: number | null; expired_units: number; disposed_units: number; donated_units: number; waste_units: number }

export type ProductInput = Omit<Product, 'product_id' | 'reorder_level' | 'units_per_box' | 'storage_section' | 'shelf_number' | 'aisle'> & { storage_section?: string; shelf_number?: string; aisle?: string; reorder_level?: number; units_per_box?: number; boxed_units?: number; unit_price?: number; box_unit_cost?: number; batch_number?: string; manufacturing_date?: string; expiry_date?: string }
export type CustomerInput = Omit<Customer, 'customer_id'>
export type SupplierInput = Omit<Supplier, 'supplier_id'>

const API_URL = import.meta.env.DEV ? '/api' : import.meta.env.VITE_API_URL ?? '/api'
let pendingRequests = 0

function publishNetworkActivity() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('pantryos:network-activity', { detail: { active: pendingRequests > 0 } }))
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  pendingRequests += 1
  publishNetworkActivity()
  try {
  const token = localStorage.getItem('pantryos_token')
  let response: Response
  try {
    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData
    response = await fetch(`${API_URL}${path}`, { ...options, headers: { ...(!isFormData ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers } })
  } catch { throw new Error('Connection lost. Check the warehouse server and try again.') }
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string | Array<{ msg?: string }> | Record<string, unknown> } | null
    const detail = Array.isArray(payload?.detail) ? payload.detail.map((item) => item.msg).filter(Boolean).join(', ') : typeof payload?.detail === 'string' ? payload.detail : undefined
    if (response.status === 401) {
      localStorage.removeItem('pantryos_token')
      window.dispatchEvent(new Event('pantryos:session-expired'))
    }
    throw new Error(detail ?? (response.status === 401 ? 'Your session has expired. Please sign in again.' : 'Request failed'))
  }
  return await response.json() as T
  } finally {
    pendingRequests = Math.max(0, pendingRequests - 1)
    publishNetworkActivity()
  }
}

export async function pingServer() {
  try {
    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), 6000)
    const response = await fetch(`${API_URL}/health`, { cache: 'no-store', signal: controller.signal })
    window.clearTimeout(timer)
    return response.ok
  } catch { return false }
}

export async function getDashboard() {
  return api<DashboardData>('/dashboard/')
}

export async function login(email: string, password: string) {
  const result = await api<{ access_token: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  localStorage.setItem('pantryos_token', result.access_token)
  return getCurrentUser()
}

export async function requestSignupOtp(email: string) { return api<{ message: string; dev_otp?: string }>('/auth/signup-otp', { method: 'POST', body: JSON.stringify({ email }) }) }
export async function register(input: { username?: string; full_name: string; email?: string; otp?: string; password: string; role: Role; warehouse_id?: number; warehouse_name?: string }) {
  return api<{ message: string; request_id?: number; user_id?: number; username: string; role: Role; warehouse_id?: number; status: string }>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}
export async function requestPasswordReset(email: string) { return api<{ message: string; dev_otp?: string }>('/auth/password-reset/request', { method: 'POST', body: JSON.stringify({ email }) }) }
export async function resetPassword(input: { email: string; otp: string; new_password: string }) { return api<{ message: string }>('/auth/password-reset/confirm', { method: 'POST', body: JSON.stringify(input) }) }
export async function getSignupWarehouses() { return api<{ warehouses: Warehouse[] }>('/auth/warehouses') }

export async function getCurrentUser() {
  return api<AuthUser>('/auth/me')
}

export async function getRegistrationRequests() { return api<{ requests: RegistrationRequest[] }>('/auth/registration-requests') }
export async function approveRegistration(requestId: number) { return api<Record<string, unknown>>(`/auth/registration-requests/${requestId}/approve`, { method: 'PATCH' }) }
export async function rejectRegistration(requestId: number) { return api<Record<string, unknown>>(`/auth/registration-requests/${requestId}/reject`, { method: 'PATCH' }) }

export function logout() {
  const token = localStorage.getItem('pantryos_token')
  localStorage.removeItem('pantryos_token')
  if (token) {
    void fetch(`${API_URL}/auth/logout`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } }).catch(() => undefined)
  }
}

export async function getProducts() { return api<{ products: Product[] }>('/products/') }
export async function getInventory() { return api<{ inventory: InventoryRecord[] }>('/inventory/') }
export async function getOperationalMetrics() { return api<OperationalMetrics>('/inventory/reports/operations') }
export async function getPutawayQueue() { return api<{ items: PutawayTask[] }>('/inventory/putaway-queue') }
export async function confirmPutaway(inventoryId: number, input: { storage_zone: string; location_code: string }) { return api<Record<string, unknown>>(`/inventory/${inventoryId}/putaway`, { method: 'PATCH', body: JSON.stringify(input) }) }
export async function getTemperatureLogs() { return api<{ logs: TemperatureLog[] }>('/inventory/temperature-logs') }
export async function recordTemperature(batchId: number, temperature_c: number) { return api<{ batch_id: number; temperature_c: number; within_range: boolean; batch_status: string }>(`/inventory/batches/${batchId}/temperature`, { method: 'POST', body: JSON.stringify({ temperature_c }) }) }
export async function updateBatchStatus(batchId: number, status: 'active' | 'quarantined' | 'disposed' | 'donated', reason: string) { return api<Record<string, unknown>>(`/inventory/batches/${batchId}/status`, { method: 'PATCH', body: JSON.stringify({ status, reason }) }) }
export async function getWarehouses() { return api<{ warehouses: Warehouse[] }>('/warehouses/') }
export async function getCustomers() { return api<{ customers: Customer[] }>('/customers/') }
export async function getSuppliers() { return api<{ suppliers: Supplier[] }>('/suppliers/') }
export async function getUsers() { return api<{ users: User[] }>('/users/') }
export async function deleteUser(userId: number, password?: string) { return api<{ message: string; user_id: number }>(`/users/${userId}/remove`, { method: 'POST', ...(password ? { body: JSON.stringify({ password }) } : {}) }) }
export async function deleteOwnAccount(password: string) { return api<{ message: string }>('/users/me/remove', { method: 'POST', body: JSON.stringify({ password }) }) }
export async function getNotifications() { return api<{ notifications: Notification[] }>('/notifications/') }
export async function markNotificationRead(notificationId: number) { return api<{ notification_id: number; is_read: boolean }>(`/notifications/${notificationId}/read`, { method: 'PATCH' }) }
export async function getMessageContacts() { return api<{ contacts: MessageContact[] }>('/notifications/contacts') }
export async function getMessages() { return api<{ messages: IncomingMessage[] }>('/notifications/messages') }
export async function sendMessage(input: { recipient_ids?: number[]; subject: string; body: string; broadcast?: boolean; reply_to_id?: number }) { return api<{ message: string; recipient_count: number }>('/notifications/messages', { method: 'POST', body: JSON.stringify(input) }) }
export async function markMessageRead(messageId: number) { return api<{ message_id: number; is_read: boolean }>(`/notifications/messages/${messageId}/read`, { method: 'PATCH' }) }
export async function getInvoices() { return api<{ invoices: Invoice[] }>('/invoices/') }
export async function getInvoiceReport(period: InvoiceReportPeriod) { return api<InvoiceReport>(`/invoices/reports/${period}`) }
export async function summarizeInvoiceReport(period: InvoiceReportPeriod) { return api<{ summary: string; ai_powered: boolean }>(`/invoices/reports/${period}/summary`, { method: 'POST' }) }
export async function getExpiringInventory(days = 7) { return api<{ days: number; items: Array<{ inventory_id: number; product_id: number; product_name: string; warehouse_id: number; batch_id: number; batch_number: string; quantity: number; expiry_date: string; status: string; days_remaining: number; estimated_value: number }> }>(`/inventory/expiring?days=${days}`) }
export async function getExpiredInventory() { return api<{ items: Array<{ inventory_id: number; product_id: number; product_name: string; batch_id: number; batch_number: string; quantity: number; expiry_date: string; status: string; estimated_value: number }> }>('/inventory/expired') }
export async function getCounterInventory() { return api<{ inventory: CounterInventory[] }>('/counter/inventory') }
export async function setCounterMinimum(input: { product_id: number; minimum_level: number }) { return api<{ product_id: number; minimum_level: number }>('/counter/minimum', { method: 'PATCH', body: JSON.stringify(input) }) }
export async function checkoutCounter(input: { request_key: string; items: Array<{ scanned_code: string; quantity: number }> }) { return api<CounterSale>('/counter/checkout', { method: 'POST', body: JSON.stringify(input) }) }
export async function lookupCounterBarcode(barcode: string) { return api<{ serial_number: string; product_id: number; product_name: string; unit_price: number; available_quantity: number; expiry_date: string; batch_number: string }>(`/counter/lookup?barcode=${encodeURIComponent(barcode)}`) }
export async function getCounterSales() { return api<{ sales: CounterSale[] }>('/counter/sales') }
export async function loginCashier(cashierId: string) { const result = await api<{ access_token: string }>('/auth/cashier-login', { method: 'POST', body: JSON.stringify({ cashier_id: cashierId }) }); localStorage.setItem('pantryos_token', result.access_token); return getCurrentUser() }
export async function getCashiers() { return api<{ cashiers: Cashier[] }>('/cashiers') }
export async function createCashier(input: { full_name: string; cashier_id?: string }) { return api<{ user_id: number; full_name: string; cashier_id: string }>('/cashiers', { method: 'POST', body: JSON.stringify(input) }) }
export async function deleteCashier(userId: number) { return api<{ message: string }>(`/cashiers/${userId}`, { method: 'DELETE' }) }
export async function getAvailableBatches() { return api<{ items: AvailableBatch[] }>('/store-orders/available') }
export async function getStoreOrders() { return api<{ orders: StoreOrder[] }>('/store-orders/') }
export async function createStoreOrder(input: { inventory_id: number; quantity: number; needed_by: string }) { return api<{ store_order_id: number; status: string; serial_number: string }>('/store-orders/', { method: 'POST', body: JSON.stringify(input) }) }
export async function updateStoreOrder(id: number, action: 'dispatch' | 'reject' | 'cancel' | 'receive') { return api<{ store_order_id: number; status: string }>(`/store-orders/${id}/${action}`, { method: 'PATCH' }) }
export async function getWarehouseCopilot(question: string) { return api<{ answer: string; priorities: string[]; ai_powered: boolean }>(`/counter/copilot?question=${encodeURIComponent(question)}`) }
export async function reduceInventoryByBarcode(input: { scanned_code: string; quantity: number; scan_event_id: string }) { return api<{ message: string; product_name: string; batch_number?: string; quantity_removed: number; remaining_quantity: number; remaining_barcode_units?: number; duplicate: boolean }>('/inventory/scan-reduction', { method: 'POST', body: JSON.stringify(input) }) }
export async function getProductInventory(productId: number) { return api<{ product_id: number; inventory: InventoryRecord[] }>(`/inventory/product/${productId}`) }
export async function getFefo(productId: number) { return api<{ product_id: number; batches: Array<{ inventory_id: number; warehouse_id: number; batch_id: number; batch_number: string; quantity: number; expiry_date: string }> }>(`/inventory/fefo/${productId}`) }
export async function getOrder(orderId: number) { return api<{ order_id: number; customer_id: number; created_by: number; status: string; created_at: string; items: Array<{ product_id: number; product_name: string; quantity: number; unit_price: number }>; fefo_allocations: Array<{ product_id: number; product_name: string; allocations: Array<{ inventory_id: number; batch_id: number; batch_number: string; quantity: number; expiry_date: string }> }> }>(`/orders/${orderId}`) }
export async function getOrders() { return api<{ orders: SalesOrder[] }>('/orders/') }
export async function scanOrderPick(orderId: number, input: { scanned_code: string; quantity: number; event_key: string }) { return api<{ message: string; duplicate: boolean; product_id?: number; batch_number?: string; expiry_date?: string; location_code?: string; picked_quantity?: number; requested_quantity?: number }>(`/orders/${orderId}/pick-scan`, { method: 'POST', body: JSON.stringify(input) }) }
export async function getInvoice(invoiceId: number) { return api<Invoice>(`/invoices/${invoiceId}`) }
export async function getLowStock() { return api<{ low_stock: Array<Product & { current_quantity: number }> }>('/products/low-stock') }
export async function createCustomer(input: CustomerInput) { return api<Customer>('/customers/', { method: 'POST', body: JSON.stringify(input) }) }
export async function createSupplier(input: SupplierInput) { return api<Supplier>('/suppliers/', { method: 'POST', body: JSON.stringify(input) }) }
export async function createOrder(input: { customer_id?: number; customer_name?: string; items: Array<{ product_id: number; quantity: number }> }) { return api<Record<string, unknown>>('/orders/', { method: 'POST', body: JSON.stringify(input) }) }
export async function createPurchaseOrder(input: { supplier_id?: number; supplier_name?: string; items: Array<{ product_id?: number; product_name?: string; quantity: number }> }) { return api<Record<string, unknown>>('/purchase-orders/', { method: 'POST', body: JSON.stringify(input) }) }
export async function cancelPurchaseOrder(purchaseOrderId: number) { return api<{ purchase_order_id: number; status: string }>(`/purchase-orders/${purchaseOrderId}/cancel`, { method: 'PATCH' }) }
export async function getPurchaseOrders() { return api<{ purchase_orders: PurchaseOrder[] }>('/purchase-orders/') }
export async function createTransfer(input: { product_id: number; batch_id: number; source_warehouse_id: number; destination_warehouse_id: number; quantity: number }) { return api<Record<string, unknown>>('/stock-transfers/', { method: 'POST', body: JSON.stringify(input) }) }
export async function getTransfers() { return api<{ transfers: StockTransfer[] }>('/stock-transfers/') }
export async function approveOrder(orderId: number) { return api<Record<string, unknown>>(`/orders/${orderId}/approve`, { method: 'PATCH' }) }
export async function rejectOrder(orderId: number) { return api<Record<string, unknown>>(`/orders/${orderId}/reject`, { method: 'PATCH' }) }
export async function cancelOrder(orderId: number) { return api<Record<string, unknown>>(`/orders/${orderId}/cancel`, { method: 'PATCH' }) }
export async function fulfillOrder(orderId: number) { return api<Record<string, unknown>>(`/orders/${orderId}/fulfill`, { method: 'PATCH' }) }
export async function confirmOrderReceipt(orderId: number) { return api<Record<string, unknown>>(`/orders/${orderId}/confirm-receipt`, { method: 'PATCH' }) }
export async function getInventoryAdditionRequests() { return api<{ requests: InventoryRequest[] }>('/inventory/addition-requests') }
export async function getInventoryRecommendations() { return api<{ recommendations: InventoryRecommendation[] }>('/inventory/recommendations/') }
export async function reviewInventoryRecommendation(recommendationId: number, decision: 'approve' | 'reject', supplierId?: number) { return api<{ recommendation_id: number; status: string; purchase_order_id?: number | null }>(`/inventory/recommendations/${recommendationId}/${decision}`, { method: 'PATCH', ...(supplierId ? { body: JSON.stringify({ supplier_id: supplierId }) } : {}) }) }
export async function createInventoryAdditionRequest(input: { product_name: string; category: string; quantity: number; units_per_box: number; boxed_units: number; unit_price: number; box_unit_cost: number }) { return api<Record<string, unknown>>('/inventory/addition-requests', { method: 'POST', body: JSON.stringify(input) }) }
export async function approveInventoryAddition(requestId: number) { return api<Record<string, unknown>>(`/inventory/addition-requests/${requestId}/approve`, { method: 'PATCH' }) }
export async function receiveInventoryAddition(requestId: number, input: { serial_number: string; batch_number: string; manufacturing_date: string; expiry_date: string; aisle: string; shelf_number: string }) { return api<Record<string, unknown>>(`/inventory/addition-requests/${requestId}/receive`, { method: 'PATCH', body: JSON.stringify(input) }) }
export async function rejectInventoryAddition(requestId: number) { return api<Record<string, unknown>>(`/inventory/addition-requests/${requestId}/reject`, { method: 'PATCH' }) }
export async function receivePurchaseOrder(purchaseOrderId: number, input: { warehouse_id: number; items: Array<{ product_id?: number; product_name?: string; quantity: number; batch_number: string; manufacturing_date: string; expiry_date: string; storage_zone: 'AMBIENT' | 'CHILLED' | 'FROZEN'; temperature_c: number }> }) { return api<{ quarantined_batches?: string[] }>(`/purchase-orders/${purchaseOrderId}/receive`, { method: 'PATCH', body: JSON.stringify(input) }) }
export async function parseDeliveryDocument(purchaseOrderId: number, document: File) { const form = new FormData(); form.append('document', document); return api<{ purchase_order_id: number; extracted: { vendor?: string; invoice_date?: string; needs_review: boolean; items: Array<{ item_name: string | null; quantity: string | null; lot_number: string | null; expiry_date: string | null }> } }>(`/purchase-orders/${purchaseOrderId}/parse-document`, { method: 'POST', body: form }) }
export async function approveTransfer(transferId: number) { return api<Record<string, unknown>>(`/stock-transfers/${transferId}/approve`, { method: 'PATCH' }) }
export async function rejectTransfer(transferId: number) { return api<Record<string, unknown>>(`/stock-transfers/${transferId}/reject`, { method: 'PATCH' }) }
export async function generateInvoice(orderId: number) { return api<Invoice>(`/invoices/generate/${orderId}`, { method: 'POST' }) }
export async function sendInvoice(invoiceId: number) { return api<Record<string, unknown>>(`/invoices/${invoiceId}/send`, { method: 'PATCH' }) }
export async function confirmInvoice(invoiceId: number) { return api<Record<string, unknown>>(`/invoices/${invoiceId}/confirm`, { method: 'PATCH' }) }
