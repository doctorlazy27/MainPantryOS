// @ts-nocheck
import { FormEvent, useState } from 'react'
import { ArrowDownToLine, CheckCircle2, RefreshCw, Send, Store } from 'lucide-react'
import { approveCounterAllocation, CounterAllocation, CounterInventory, getCounterAllocations, getCounterInventory, getProducts, Product, rejectCounterAllocation, requestCounterAllocation, Role } from './api'
import AppSelect from './AppSelect'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { role: Role; onToast: (message: string) => void }

export default function CounterStockPanel({ role, onToast }: Props) {
  const [stock, setStock] = useState<CounterInventory[]>([])
  const [allocations, setAllocations] = useState<CounterAllocation[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [product, setProduct] = useState('')
  const [quantity, setQuantity] = useState('25')

  async function load() {
    try {
      const [counter, requests, catalog] = await Promise.all([getCounterInventory(), getCounterAllocations(), getProducts()])
      setStock(counter.inventory)
      setAllocations(requests.allocations)
      setProducts(catalog.products)
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load counter stock') }
  }

  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading counter stock" />

  async function request(event: FormEvent) {
    event.preventDefault()
    try {
      await requestCounterAllocation({ product_id: Number(product), quantity: Number(quantity) })
      onToast(role === 'manager' ? 'Warehouse stock moved to the counter using FEFO' : 'Counter replenishment sent for manager approval')
      setProduct('')
      await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not request allocation') }
  }

  async function approve(id: number) {
    try { await approveCounterAllocation(id); onToast('Warehouse stock transferred to counter using FEFO'); await load() }
    catch (error) { onToast(error instanceof Error ? error.message : 'Could not approve allocation') }
  }

  async function reject(id: number) {
    try { await rejectCounterAllocation(id); onToast('Counter replenishment rejected'); await load() }
    catch (error) { onToast(error instanceof Error ? error.message : 'Could not reject allocation') }
  }

  const pending = allocations.filter((item) => item.status === 'pending')

  return <>
    <section className="module-header"><div><p className="eyebrow">Store zone</p><h1>Counter Stock</h1><p>Managers issue stock from warehouse shelves; each scan sells one unit from this counter balance.</p></div><button className="button subtle" onClick={() => void load()}><RefreshCw size={16} /> Refresh</button></section>
    <section className="panel counter-grid"><div className="counter-summary"><Store size={22} /><strong>{stock.reduce((sum, item) => sum + item.quantity, 0)}</strong><span>units at counter</span></div><div className="counter-summary"><ArrowDownToLine size={22} /><strong>{pending.length}</strong><span>pending allocations</span></div></section>
    <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Live counter shelf</p><h2>Products available to sell</h2></div></div>{stock.length ? <div className="counter-stock-list">{stock.map((item) => { const productRecord = products.find((productItem) => productItem.product_id === item.product_id); return <article className="counter-stock-item" key={item.counter_inventory_id}><div className="counter-product-icon"><Store size={17} /></div><div><strong>{item.product_name}</strong><small>{productRecord?.storage_section ?? item.category} · shelf {productRecord?.shelf_number ?? 'Unassigned'} · {item.batch_number}</small></div><div className="counter-quantity"><strong>{item.quantity}</strong><small>min {item.minimum_level}</small></div><span className={`pill ${item.status === 'GOOD' ? 'ready' : 'urgent'}`}>{item.status}</span></article> })}</div> : <div className="empty-state"><Store size={28} /><strong>Counter is empty</strong><span>Issue an allocation to place warehouse stock at the counter.</span></div>}</section>
    {(role === 'manager' || role === 'warehouse_worker') && <section className="panel workflow-card counter-request"><p className="eyebrow">{role === 'manager' ? 'Manager issue' : 'Worker task'}</p><h2>{role === 'manager' ? 'Issue stock to counter' : 'Request counter replenishment'}</h2><p>{role === 'manager' ? 'Move the requested amount from warehouse inventory using earliest-expiry stock first.' : 'Use this when the shelf is low. A manager approves the warehouse-to-counter transfer.'}</p><form className="form-grid" onSubmit={request}><label>Product<AppSelect required value={product} onChange={(event) => setProduct(event.target.value)}><option value="">Select product</option>{products.map((item) => <option key={item.product_id} value={item.product_id}>{item.name} · {item.category}</option>)}</AppSelect></label><label>Units<input required type="number" min="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label><button className="button primary" type="submit"><Send size={16} /> {role === 'manager' ? 'Issue stock' : 'Request allocation'}</button></form></section>}
    {role === 'manager' && <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Worker requests</p><h2>Replenishment required</h2></div></div>{pending.length ? pending.map((item) => <div className="data-row compact" key={item.allocation_id}><strong>{item.product_name}</strong><span>{item.quantity} units requested</span><button className="row-action" onClick={() => void approve(item.allocation_id)}><CheckCircle2 size={14} /> Approve</button><button className="row-action danger" onClick={() => void reject(item.allocation_id)}>Reject</button></div>) : <div className="empty-state"><CheckCircle2 size={25} /><strong>No pending allocations</strong><span>Worker replenishment requests will appear here.</span></div>}</section>}
  </>
}