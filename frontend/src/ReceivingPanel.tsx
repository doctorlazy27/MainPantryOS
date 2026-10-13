import { FormEvent, useEffect, useState } from 'react'
import { ArrowDownToLine, CheckCircle2, Plus, RefreshCw } from 'lucide-react'
import { cancelPurchaseOrder, confirmPutaway, createPurchaseOrder, getCurrentUser, getProducts, getPurchaseOrders, getPutawayQueue, parseDeliveryDocument, Product, PurchaseOrder, PutawayTask, receivePurchaseOrder, Role } from './api'
import AppSelect from './AppSelect'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { role: Role; onToast: (message: string) => void }
type BatchDetails = { number: string; manufactured: string; expiry: string; storageZone: 'AMBIENT' | 'CHILLED' | 'FROZEN'; temperature: string }
const emptyBatchDetails: BatchDetails = { number: '', manufactured: '', expiry: '', storageZone: 'AMBIENT', temperature: '20' }

export default function ReceivingPanel({ role, onToast }: Props) {
  const [supplier, setSupplier] = useState('')
  const [product, setProduct] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [products, setProducts] = useState<Product[]>([])
  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [selectedOrder, setSelectedOrder] = useState<PurchaseOrder | null>(null)
  const [warehouseId, setWarehouseId] = useState<number | null>(null)
  const [batchDetails, setBatchDetails] = useState<Record<string, BatchDetails>>({})
  const [putawayItems, setPutawayItems] = useState<PutawayTask[]>([])
  const [putawayLocations, setPutawayLocations] = useState<Record<number, string>>({})
  const [deliveryDocument, setDeliveryDocument] = useState<File | null>(null)
  const [ocrResult, setOcrResult] = useState<Awaited<ReturnType<typeof parseDeliveryDocument>>['extracted'] | null>(null)

  const load = async () => {
    try {
      const [orderData, productData, user, putawayData] = await Promise.all([getPurchaseOrders(), getProducts(), getCurrentUser(), getPutawayQueue()])
      setOrders(orderData.purchase_orders)
      setProducts(productData.products)
      setWarehouseId(user.warehouse_id)
      setPutawayItems(putawayData.items)
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load receiving queue') }
  }
  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading receiving queue" />

  function batchDetailsKey(orderId: number, index: number) { return `${orderId}:${index}` }

  function updateBatchDetails(orderId: number, index: number, field: keyof BatchDetails, value: string) {
    const key = batchDetailsKey(orderId, index)
    setBatchDetails((current) => ({ ...current, [key]: { ...emptyBatchDetails, ...current[key], [field]: value } }))
  }

  async function create(event: FormEvent) {
    event.preventDefault()
    try {
      await createPurchaseOrder({ supplier_name: supplier.trim(), items: [{ product_id: Number(product), quantity: Number(quantity) }] })
      onToast('Purchase request sent to the warehouse queue')
      setSupplier(''); setProduct(''); setQuantity('1'); await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not create purchase request') }
  }

  async function cancelPendingPurchaseOrder(purchaseOrderId: number) {
    try { await cancelPurchaseOrder(purchaseOrderId); onToast(`Purchase order #${purchaseOrderId} cancelled`); await load() }
    catch (error) { onToast(error instanceof Error ? error.message : 'Could not cancel purchase order') }
  }

  async function receive(event: FormEvent) {
    event.preventDefault()
    if (!selectedOrder || !warehouseId) return
    const receivingItems = selectedOrder.items.map((item, index) => {
      const details = batchDetails[batchDetailsKey(selectedOrder.purchase_order_id, index)] ?? emptyBatchDetails
      return { product_id: item.product_id, quantity: item.quantity, batch_number: details.number.trim(), manufacturing_date: details.manufactured, expiry_date: details.expiry, storage_zone: details.storageZone, temperature_c: Number(details.temperature) }
    })
    const invalidLine = receivingItems.find((item) => !item.batch_number || !item.manufacturing_date || !item.expiry_date || new Date(`${item.expiry_date}T00:00:00`) <= new Date(`${item.manufacturing_date}T00:00:00`) || !Number.isFinite(item.temperature_c) || item.temperature_c < -80 || item.temperature_c > 100)
    if (invalidLine) { onToast('Enter valid batch dates, temperature, and a unique lot number for every line'); return }
    try {
      const result = await receivePurchaseOrder(selectedOrder.purchase_order_id, { warehouse_id: warehouseId, items: receivingItems })
      onToast(result.quarantined_batches?.length ? `Received with QC hold: ${result.quarantined_batches.join(', ')}` : `Purchase order #${selectedOrder.purchase_order_id} received; stock is waiting for putaway`)
      setSelectedOrder(null); setBatchDetails({}); await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not receive purchase order') }
  }

  async function confirmLocation(item: PutawayTask) {
    const locationCode = putawayLocations[item.inventory_id]?.trim()
    if (!locationCode) { onToast('Scan or enter the destination shelf/bin'); return }
    try {
      await confirmPutaway(item.inventory_id, { storage_zone: item.storage_zone, location_code: locationCode })
      onToast(`${item.product_name} put away at ${item.storage_zone}/${locationCode}`)
      setPutawayLocations({ ...putawayLocations, [item.inventory_id]: '' })
      await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not confirm putaway') }
  }

  async function parseDocument() {
    if (!selectedOrder || !deliveryDocument) { onToast('Select a pending order and delivery document first'); return }
    try {
      const result = await parseDeliveryDocument(selectedOrder.purchase_order_id, deliveryDocument)
      setOcrResult(result.extracted)
      setBatchDetails((current) => {
        const next = { ...current }
        result.extracted.items.forEach((detected, detectedIndex) => {
          const matchIndex = detected.item_name
            ? selectedOrder.items.findIndex((item) => item.product_name.toLowerCase() === detected.item_name?.toLowerCase())
            : -1
          const lineIndex = matchIndex >= 0 ? matchIndex : detectedIndex < selectedOrder.items.length ? detectedIndex : -1
          if (lineIndex < 0) return
          const key = batchDetailsKey(selectedOrder.purchase_order_id, lineIndex)
          next[key] = { ...emptyBatchDetails, ...next[key], number: detected.lot_number ?? next[key]?.number ?? '', expiry: dateInputValue(detected.expiry_date) || next[key]?.expiry || '' }
        })
        return next
      })
      onToast('Document parsed. Verify every extracted value against the physical delivery.')
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not parse delivery document') }
  }

  return <>
    <Header eyebrow="Inbound stock" title="Receiving" description="Managers request stock. Workers receive it, assign the physical batch, and put it into the assigned warehouse." />
    {role === 'warehouse_worker' && <section className="panel workflow-card"><p className="eyebrow">Optional document assist</p><h2>Parse a delivery invoice</h2><div className="form-grid"><label>Pending purchase order<AppSelect value={selectedOrder?.purchase_order_id ?? ''} onChange={(event) => { const order = orders.find((item) => item.purchase_order_id === Number(event.target.value)) ?? null; setSelectedOrder(order); setOcrResult(null) }}><option value="">Select an order</option>{orders.filter((item) => item.status === 'pending').map((item) => <option key={item.purchase_order_id} value={item.purchase_order_id}>#{item.purchase_order_id} · {item.supplier_name}</option>)}</AppSelect></label><label>Delivery document<input type="file" accept="application/pdf,image/jpeg,image/png,image/tiff" onChange={(event) => { setDeliveryDocument(event.target.files?.[0] ?? null); setOcrResult(null) }} /></label><button className="button subtle" disabled={!selectedOrder || !deliveryDocument} onClick={() => void parseDocument()}>Extract with AWS Textract</button></div>{ocrResult && <div className="field-hint"><strong>Review before receiving · {ocrResult.vendor ?? 'Vendor not detected'}</strong>{ocrResult.items.map((item, index) => <p key={index}>{item.item_name ?? 'Item not detected'} · qty {item.quantity ?? '?'} · lot {item.lot_number ?? 'not detected'} · expiry {item.expiry_date ?? 'not detected'}</p>)}</div>}</section>}
    {role === 'warehouse_worker' && <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Step 3 · Putaway</p><h2>Staged stock</h2></div><span className="table-count">{putawayItems.length} batches waiting</span></div>{putawayItems.length ? putawayItems.map((item) => <form className="data-row compact" key={item.inventory_id} onSubmit={(event) => { event.preventDefault(); void confirmLocation(item) }}><strong>{item.product_name} · {item.batch_number}</strong><span>{item.quantity} units · {item.storage_zone}</span><label>Destination bin<input autoComplete="off" required placeholder="Scan shelf/bin code" value={putawayLocations[item.inventory_id] ?? ''} onChange={(event) => setPutawayLocations({ ...putawayLocations, [item.inventory_id]: event.target.value })} /></label><button className="row-action" type="submit">Confirm putaway</button></form>) : <p className="field-hint">No QC-approved stock is waiting for putaway.</p>}</section>}
    {role === 'manager' && <section className="panel workflow-card receiving-card"><div className="workflow-number"><Plus size={17} /></div><p className="eyebrow">Step 1 · Manager</p><h2>Request inbound stock</h2><p>Create a purchase request for the warehouse. No inventory or batch is created until the delivery is physically received.</p><form className="stack-form" onSubmit={create}><label>Supplier name<input required value={supplier} placeholder="e.g. Green Valley Foods" onChange={(event) => setSupplier(event.target.value)} /></label><label>Product<AppSelect required value={product} onChange={(event) => setProduct(event.target.value)}><option value="">Select food item</option>{products.map((item) => <option value={item.product_id} key={item.product_id}>{item.name} · {item.category}</option>)}</AppSelect></label><label>Expected quantity<input required type="number" min="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label><button className="button primary" type="submit"><Plus size={16} /> Send purchase request</button></form></section>}
    {role === 'manager' && <PendingPurchaseOrderQueue orders={orders.filter((item) => item.status === 'pending')} onCancel={(id) => void cancelPendingPurchaseOrder(id)} />}
    {role === 'warehouse_worker' && <><section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Step 2 · Worker</p><h2>Inbound queue</h2><span className="table-count">{orders.filter((item) => item.status === 'pending').length} waiting for receipt</span></div><button className="button subtle" onClick={() => void load()}><RefreshCw size={15} /> Refresh</button></div>{orders.filter((item) => item.status === 'pending').length ? <div className="receiving-queue">{orders.filter((item) => item.status === 'pending').map((item) => <button className={`receiving-order ${selectedOrder?.purchase_order_id === item.purchase_order_id ? 'selected' : ''}`} key={item.purchase_order_id} onClick={() => setSelectedOrder(item)}><span className="order-icon"><ArrowDownToLine size={17} /></span><span><strong>Purchase #{item.purchase_order_id}</strong><small>{item.supplier_name} · {item.items.map((line) => `${line.product_name} x${line.quantity}`).join(', ')}</small></span><span className="pill pending">Pending</span></button>)}</div> : <div className="empty-state"><CheckCircle2 size={27} /><strong>Receiving queue is clear</strong><span>New manager purchase requests will appear here.</span></div>}</section>{selectedOrder && <section className="panel workflow-card receiving-card"><div className="workflow-number"><ArrowDownToLine size={17} /></div><p className="eyebrow">Step 3 · Receive and identify</p><h2>Receive purchase #{selectedOrder.purchase_order_id}</h2><p>Enter lot and quality details separately for every purchase-order line. Out-of-range deliveries are quarantined for manager review.</p><form className="stack-form" onSubmit={receive}>{selectedOrder.items.map((item, index) => <ReceivingLotFields key={`${selectedOrder.purchase_order_id}:${index}`} productName={item.product_name} quantity={item.quantity} value={batchDetails[batchDetailsKey(selectedOrder.purchase_order_id, index)] ?? emptyBatchDetails} onChange={(field, value) => updateBatchDetails(selectedOrder.purchase_order_id, index, field, value)} />)}<button className="button primary" type="submit"><CheckCircle2 size={16} /> Receive into warehouse</button></form></section>}</>}
  </>
}

function PendingPurchaseOrderQueue({ orders, onCancel }: { orders: PurchaseOrder[]; onCancel: (id: number) => void }) {
  if (!orders.length) return null
  return <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Inbound orders</p><h2>Pending deliveries</h2></div></div>{orders.map((order) => <div className="data-row compact" key={order.purchase_order_id}><strong>Purchase #{order.purchase_order_id}</strong><span>{order.supplier_name}</span><span>{order.items.map((item) => `${item.product_name} x${item.quantity}`).join(', ')}</span><button className="row-action danger" onClick={() => onCancel(order.purchase_order_id)}>Cancel order</button></div>)}</section>
}

function Header({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) { return <section className="module-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div></section> }

function dateInputValue(value: string | null | undefined) {
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : ''
}

function ReceivingLotFields({ productName, quantity, value, onChange }: { productName: string; quantity: number; value: BatchDetails; onChange: (field: keyof BatchDetails, value: string) => void }) {
  return <fieldset className="receiving-lot-fields"><legend>{productName} x{quantity}</legend><div className="form-grid"><label>Batch number<input required value={value.number} onChange={(event) => onChange('number', event.target.value)} /></label><label>Manufacturing date<input required type="date" value={value.manufactured} onChange={(event) => onChange('manufactured', event.target.value)} /></label><label>Expiry date<input required type="date" value={value.expiry} onChange={(event) => onChange('expiry', event.target.value)} /></label><label>Storage zone<AppSelect value={value.storageZone} onChange={(event) => onChange('storageZone', event.target.value)}><option value="AMBIENT">Ambient</option><option value="CHILLED">Chilled</option><option value="FROZEN">Frozen</option></AppSelect></label><label>Delivery temperature (C)<input required type="number" min="-80" max="100" step="0.1" value={value.temperature} onChange={(event) => onChange('temperature', event.target.value)} /></label></div></fieldset>
}
