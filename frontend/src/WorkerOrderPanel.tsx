import { FormEvent, useEffect, useState } from 'react'
import { fulfillOrder, getOrders, scanOrderPick } from './api'

type Props = { onToast: (message: string) => void }

export default function WorkerOrderPanel({ onToast }: Props) {
  const [orders, setOrders] = useState<Awaited<ReturnType<typeof getOrders>>['orders']>([])
  const [codes, setCodes] = useState<Record<number, string>>({})
  const [quantities, setQuantities] = useState<Record<number, string>>({})
  const load = async () => { try { setOrders((await getOrders()).orders.filter((order) => order.status === 'approved' && order.reservation_status !== 'short')) } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load warehouse orders') } }
  useEffect(() => { void load() }, [])
  async function scan(event: FormEvent, orderId: number) {
    event.preventDefault()
    const scannedCode = codes[orderId]?.trim()
    const quantity = Number(quantities[orderId] ?? '1')
    if (!scannedCode || !Number.isInteger(quantity) || quantity < 1) { onToast('Scan a barcode and enter a valid quantity'); return }
    try {
      const result = await scanOrderPick(orderId, { scanned_code: scannedCode, quantity, event_key: crypto.randomUUID() })
      onToast(result.duplicate ? 'This scan was already recorded' : `Verified batch ${result.batch_number} at ${result.location_code}`)
      setCodes({ ...codes, [orderId]: '' })
      await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Pick scan failed') }
  }
  async function dispatch(orderId: number) {
    try { await fulfillOrder(orderId); onToast(`Order #${orderId} dispatched`); await load() }
    catch (error) { onToast(error instanceof Error ? error.message : 'Dispatch failed') }
  }
  return <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">FEFO pick and dispatch</p><h2>Approved orders</h2></div><button className="button subtle" onClick={() => void load()}>Refresh</button></div>{orders.length ? orders.map((order) => {
    const complete = order.items.every((item) => (order.pick_progress?.[item.product_id] ?? 0) >= item.quantity)
    return <article className="panel workflow-card" key={order.order_id}><div className="table-toolbar"><div><p className="eyebrow">Order #{order.order_id}</p><h3>Customer #{order.customer_id}</h3></div><span className="pill ready">Picking</span></div><div className="data-table">{order.items.map((item) => { const picked = order.pick_progress?.[item.product_id] ?? 0; return <div className="data-row compact" key={item.product_id}><strong>{item.product_name}</strong><span>{picked} / {item.quantity} picked</span><span>FEFO enforced</span></div>})}</div><form className="form-grid" onSubmit={(event) => void scan(event, order.order_id)}><label>Scan item barcode or batch number<input autoComplete="off" autoFocus value={codes[order.order_id] ?? ''} onChange={(event) => setCodes({ ...codes, [order.order_id]: event.target.value })} /></label><label>Quantity<input type="number" min="1" value={quantities[order.order_id] ?? '1'} onChange={(event) => setQuantities({ ...quantities, [order.order_id]: event.target.value })} /></label><button className="button primary" type="submit">Verify pick</button></form><button className="button primary" disabled={!complete} onClick={() => void dispatch(order.order_id)}>{complete ? 'Confirm packing and dispatch' : 'Complete all item scans to dispatch'}</button></article>
  }) : <p className="field-hint">No approved orders are waiting to be picked.</p>}</section>
}
