// @ts-nocheck
import { FormEvent, useState } from 'react'
import { Truck } from 'lucide-react'
import { approveTransfer, AuthUser, createTransfer, getCurrentUser, getFefo, getProducts, getTransfers, getWarehouses, Product, rejectTransfer, Role, StockTransfer, Warehouse } from './api'
import AppSelect from './AppSelect'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { onToast: (message: string) => void; role: Role }

export default function TransferPanel({ onToast, role }: Props) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [products, setProducts] = useState<Product[]>([])
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [batches, setBatches] = useState<Awaited<ReturnType<typeof getFefo>>['batches']>([])
  const [transfers, setTransfers] = useState<StockTransfer[]>([])
  const [form, setForm] = useState({ product: '', batch: '', destination: '', quantity: '1' })

  const load = async () => {
    try {
      const [productData, warehouseData, transferData, currentUser] = await Promise.all([getProducts(), getWarehouses(), getTransfers(), getCurrentUser()])
      setProducts(productData.products)
      setWarehouses(warehouseData.warehouses)
      setTransfers(transferData.transfers)
      setUser(currentUser)
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Could not load transfer queue')
    }
  }

  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading transfer queue" />

  async function submit(event: FormEvent) {
    event.preventDefault()
    try {
      if (!user?.warehouse_id) throw new Error('Your account has no assigned warehouse')
      await createTransfer({ product_id: Number(form.product), batch_id: Number(form.batch), source_warehouse_id: user.warehouse_id, destination_warehouse_id: Number(form.destination), quantity: Number(form.quantity) })
      onToast('Transfer requested')
      setForm({ product: '', batch: '', destination: '', quantity: '1' })
      setBatches([])
      await load()
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Transfer request failed')
    }
  }

  async function review(transferId: number, approve: boolean) {
    try {
      if (approve) await approveTransfer(transferId)
      else await rejectTransfer(transferId)
      onToast(approve ? 'Transfer approved' : 'Transfer rejected')
      await load()
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Transfer review failed')
    }
  }

  const sourceWarehouse = warehouses.find((warehouse) => warehouse.warehouse_id === user?.warehouse_id)
  return <><section className="module-header"><div><p className="eyebrow">Stock movement</p><h1>Transfers</h1><p>Review transfer requests for your warehouse or request a move from your assigned warehouse.</p></div><button className="button subtle" onClick={() => void load()}>Refresh</button></section>{(role === 'manager') && <section className="panel workflow-card"><p className="eyebrow">New request</p><h2>Move stock to another warehouse</h2><form className="form-grid" onSubmit={submit}><label>Product<AppSelect required value={form.product} onChange={async (event) => { const productId = event.target.value; setForm({ ...form, product: productId, batch: '' }); if (!productId) { setBatches([]); return } try { setBatches((await getFefo(Number(productId))).batches) } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load available batches') } }}><option value="">Select product</option>{products.map((product) => <option key={product.product_id} value={product.product_id}>{product.name}</option>)}</AppSelect></label><label>Available batch<AppSelect required value={form.batch} onChange={(event) => setForm({ ...form, batch: event.target.value })}><option value="">Select batch</option>{batches.map((batch) => <option key={batch.batch_id} value={batch.batch_id}>{batch.batch_number} · {batch.quantity} units · expires {batch.expiry_date}</option>)}</AppSelect></label><label>Source warehouse<input readOnly value={sourceWarehouse?.name ?? 'Loading assigned warehouse'} /></label><label>Destination warehouse<AppSelect required value={form.destination} onChange={(event) => setForm({ ...form, destination: event.target.value })}><option value="">Select destination</option>{warehouses.filter((warehouse) => warehouse.warehouse_id !== user?.warehouse_id).map((warehouse) => <option key={warehouse.warehouse_id} value={warehouse.warehouse_id}>{warehouse.name}</option>)}</AppSelect></label><label>Quantity<input required type="number" min="1" value={form.quantity} onChange={(event) => setForm({ ...form, quantity: event.target.value })} /></label><div className="form-actions"><button className="button primary" type="submit"><Truck size={16} /> Request transfer</button></div></form></section>}<section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Transfer queue</p><h2>{transfers.length} requests</h2></div></div>{transfers.length ? <div className="data-table"><div className="data-head"><span>Product / batch</span><span>Route</span><span>Quantity</span><span>Status</span><span>Action</span></div>{transfers.map((transfer) => <div className="data-row" key={transfer.transfer_id}><strong>{transfer.product_name}<small>Batch {transfer.batch_number}</small></strong><span>{transfer.source_warehouse_name} to {transfer.destination_warehouse_name}</span><span>{transfer.quantity}</span><span className={`pill ${transfer.status === 'completed' ? 'ready' : transfer.status === 'rejected' ? 'urgent' : 'pending'}`}>{transfer.status}</span><span>{role === 'manager' && transfer.status === 'pending' && <><button className="row-action" onClick={() => void review(transfer.transfer_id, true)}>Approve</button><button className="row-action danger" onClick={() => void review(transfer.transfer_id, false)}>Reject</button></>}</span></div>)}</div> : <div className="empty-state"><Truck size={28} /><strong>No transfer requests</strong><span>Requests involving your assigned warehouse will appear here.</span></div>}</section></>
}
