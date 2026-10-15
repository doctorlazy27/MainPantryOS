import { FormEvent, useState } from 'react'
import { RefreshCw, Store } from 'lucide-react'
import { CounterInventory, getCounterInventory, Role, setCounterMinimum } from './api'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { role: Role; onToast: (message: string) => void }

export default function CounterStockPanel({ onToast }: Props) {
  const [stock, setStock] = useState<CounterInventory[]>([])
  const [minimums, setMinimums] = useState<Record<number, string>>({})

  async function load() {
    try { setStock((await getCounterInventory()).inventory) }
    catch (error) { onToast(error instanceof Error ? error.message : 'Could not load counter stock') }
  }
  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading counter stock" />

  async function saveMinimum(event: FormEvent, item: CounterInventory) {
    event.preventDefault()
    const value = Number(minimums[item.product_id])
    if (!Number.isInteger(value) || value < 0) { onToast('Enter a whole number of units'); return }
    try { await setCounterMinimum({ product_id: item.product_id, minimum_level: value }); onToast(`${item.product_name} minimum set to ${value}`); setMinimums({ ...minimums, [item.product_id]: '' }); await load() }
    catch (error) { onToast(error instanceof Error ? error.message : 'Could not save the minimum') }
  }

  const low = stock.filter((item) => item.status !== 'GOOD')
  return <>
    <section className="module-header"><div><p className="eyebrow">Store zone</p><h1>Counter Stock</h1><p>Stock received from the warehouse. Each cashier sale deducts from these balances. Order more from the Store orders page.</p></div><button className="button subtle" onClick={() => void load()}><RefreshCw size={16} /> Refresh</button></section>
    <section className="panel counter-grid"><div className="counter-summary"><Store size={22} /><strong>{stock.reduce((sum, item) => sum + item.quantity, 0)}</strong><span>units at counter</span></div><div className="counter-summary"><Store size={22} /><strong>{low.length}</strong><span>products low or empty</span></div></section>
    <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Live counter shelf</p><h2>Products available to sell</h2></div></div>{stock.length ? <div className="counter-stock-list">{stock.map((item) => <article className="counter-stock-item" key={item.counter_inventory_id}><div className="counter-product-icon"><Store size={17} /></div><div><strong>{item.product_name}</strong><small>Serial {item.serial_number ?? '—'} · batch {item.batch_number}</small></div><div className="counter-quantity"><strong>{item.quantity}</strong><small>min {item.minimum_level}</small></div><span className={`pill ${item.status === 'GOOD' ? 'ready' : 'urgent'}`}>{item.status}</span><form className="inline-form" onSubmit={(event) => void saveMinimum(event, item)}><input aria-label={`Minimum for ${item.product_name}`} type="number" min="0" placeholder="Min" value={minimums[item.product_id] ?? ''} onChange={(event) => setMinimums({ ...minimums, [item.product_id]: event.target.value })} /><button className="row-action" type="submit">Set minimum</button></form></article>)}</div> : <div className="empty-state"><Store size={28} /><strong>Counter is empty</strong><span>Order a batch from the warehouse and confirm receipt to stock the counter.</span></div>}</section>
  </>
}
