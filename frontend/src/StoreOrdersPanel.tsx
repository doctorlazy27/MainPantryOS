import { FormEvent, useState } from 'react'
import { AvailableBatch, createStoreOrder, getAvailableBatches, getStoreOrders, Role, StoreOrder, updateStoreOrder } from './api'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { role: Role; onToast: (message: string) => void }

const toLocalInput = (date: Date) => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
const fmt = (value?: string | null) => value ? new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString() : '—'

export default function StoreOrdersPanel({ role, onToast }: Props) {
  const [available, setAvailable] = useState<AvailableBatch[]>([])
  const [orders, setOrders] = useState<StoreOrder[]>([])
  const [selected, setSelected] = useState<AvailableBatch | null>(null)
  const [quantity, setQuantity] = useState('1')
  const [neededBy, setNeededBy] = useState(toLocalInput(new Date(Date.now() + 4 * 3600000)))

  async function load() {
    try {
      const [batches, list] = await Promise.all([getAvailableBatches(), getStoreOrders()])
      setAvailable(batches.items); setOrders(list.orders)
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load store orders') }
  }
  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading store orders" />

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!selected) return
    try {
      await createStoreOrder({ inventory_id: selected.inventory_id, quantity: Number(quantity), needed_by: new Date(neededBy).toISOString() })
      onToast(`Ordered ${quantity} x ${selected.product_name} (serial ${selected.serial_number})`); setSelected(null); setQuantity('1'); await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not place the store order') }
  }

  async function act(order: StoreOrder, action: 'dispatch' | 'reject' | 'cancel' | 'receive') {
    try {
      await updateStoreOrder(order.store_order_id, action)
      onToast({ dispatch: 'Marked as dispatched', reject: 'Order rejected', cancel: 'Order cancelled', receive: 'Store received the batch; counter stock updated' }[action]); await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not update the store order') }
  }

  const open = orders.filter((order) => order.status === 'pending' || order.status === 'dispatched')
  const history = orders.filter((order) => !['pending', 'dispatched'].includes(order.status)).slice(0, 15)
  const lowItems = available.filter((item) => item.counter_low)

  return <>
    <section className="module-header"><div><p className="eyebrow">Warehouse to store</p><h1>Store orders</h1><p>{role === 'manager' ? 'Pick a batch by serial number, give the warehouse a delivery time, then confirm when the store receives it.' : 'Dispatch the batches the store has ordered and confirm they have left the warehouse.'}</p></div><button className="button subtle" onClick={() => void load()}>Refresh</button></section>

    {role === 'manager' && <>
      {lowItems.length > 0 && <section className="panel low-stock-panel"><div className="table-toolbar"><div><p className="eyebrow">Counter running low</p><h2>Products to reorder</h2></div></div><div className="low-stock-list">{lowItems.map((item) => <div className="low-stock-item" key={item.inventory_id}><div><strong>{item.product_name}</strong><span>{item.counter_quantity} at counter · minimum {item.counter_minimum} · serial {item.serial_number}</span></div><button className="row-action" onClick={() => { setSelected(item); setQuantity('1') }}>Order batch</button></div>)}</div></section>}
      <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Warehouse inventory</p><h2>Batches available to order</h2></div></div>{available.length ? <div className="data-table"><div className="data-head"><span>Product</span><span>Serial number</span><span>Batch</span><span>Available</span><span>At counter</span><span>Action</span></div>{available.map((item) => <div className="data-row" key={item.inventory_id}><strong>{item.product_name}</strong><span>{item.serial_number ?? '—'}</span><span>{item.batch_number}</span><span>{item.available_quantity}</span><span className={item.counter_low ? 'warning-text' : ''}>{item.counter_quantity}{item.counter_low ? ' · LOW' : ''}</span><button className="row-action" onClick={() => { setSelected(item); setQuantity('1') }}>Order batch</button></div>)}</div> : <p className="field-hint">The warehouse has no shelved stock available right now.</p>}</section>
    </>}

    <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">In progress</p><h2>{open.length} open store orders</h2></div></div>{open.length ? open.map((order) => <div className="data-row compact" key={order.store_order_id}><strong>#{order.store_order_id} · {order.product_name}</strong><span>{order.quantity} units · serial {order.serial_number} · batch {order.batch_number}</span><span>Needed by {fmt(order.needed_by)}</span><span className={`pill ${order.status === 'dispatched' ? 'ready' : ''}`}>{order.status.toUpperCase()}</span>
      {role === 'warehouse_worker' && order.status === 'pending' && <><button className="row-action" onClick={() => void act(order, 'dispatch')}>Confirm dispatched</button><button className="row-action danger" onClick={() => void act(order, 'reject')}>Reject</button></>}
      {role === 'manager' && order.status === 'pending' && <button className="row-action danger" onClick={() => void act(order, 'cancel')}>Cancel</button>}
      {role === 'manager' && order.status === 'dispatched' && <button className="row-action" onClick={() => void act(order, 'receive')}>Confirm store received</button>}
    </div>) : <p className="field-hint">No store orders are waiting.</p>}</section>

    {history.length > 0 && <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">History</p><h2>Completed and closed orders</h2></div></div>{history.map((order) => <div className="data-row compact" key={order.store_order_id}><strong>#{order.store_order_id} · {order.product_name}</strong><span>{order.quantity} units · serial {order.serial_number}</span><span>{order.status === 'received' ? `Received ${fmt(order.received_at)}` : order.status}</span></div>)}</section>}

    {selected && <div className="modal-backdrop" onMouseDown={() => setSelected(null)}><div className="modal" onMouseDown={(event) => event.stopPropagation()}><div className="modal-header"><div><p className="eyebrow">Order a batch</p><h2>{selected.product_name}</h2></div></div><p className="field-hint">Serial {selected.serial_number} · batch {selected.batch_number} · {selected.available_quantity} available</p><form className="form-grid" onSubmit={(event) => void submit(event)}><label>Units<input required type="number" min="1" max={selected.available_quantity} value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label><label>Warehouse should dispatch by<input required type="datetime-local" value={neededBy} onChange={(event) => setNeededBy(event.target.value)} /></label><div className="form-actions"><button className="button subtle" type="button" onClick={() => setSelected(null)}>Cancel</button><button className="button primary" type="submit">Send to warehouse</button></div></form></div></div>}
  </>
}
