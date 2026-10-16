import { useState } from 'react'
import { ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { getInventory, getProducts, InventoryRecord, Product, Role } from './api'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { role: Role; onToast: (message: string) => void }

const daysUntil = (date?: string | null) => date ? Math.ceil((new Date(date).getTime() - Date.now()) / 86400000) : null

export default function InventoryOverview({ onToast }: Props) {
  const [products, setProducts] = useState<Product[]>([])
  const [inventory, setInventory] = useState<InventoryRecord[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [search, setSearch] = useState('')

  const load = async () => {
    try {
      const [productResult, inventoryResult] = await Promise.all([getProducts(), getInventory()])
      setProducts(productResult.products); setInventory(inventoryResult.inventory)
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load inventory') }
  }
  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading inventory" />

  const unitsOf = (productId: number) => inventory.filter((row) => row.product_id === productId).reduce((sum, row) => sum + row.quantity, 0)
  const selected = products.find((product) => product.product_id === selectedId) ?? null

  if (selected) {
    const batches = inventory.filter((row) => row.product_id === selected.product_id).sort((a, b) => (a.expiry_date ?? '').localeCompare(b.expiry_date ?? ''))
    const total = unitsOf(selected.product_id)
    const nearest = batches.filter((row) => row.quantity > 0).map((row) => daysUntil(row.expiry_date)).filter((days): days is number => days !== null)
    return <>
      <button className="link-button" onClick={() => setSelectedId(null)}><ChevronLeft size={18} /> All products</button>
      <section className="module-header"><div><p className="eyebrow">{selected.storage_section || selected.category}</p><h1>{selected.name}</h1><p>Serial numbers are assigned per batch.</p></div></section>
      <section className="stat-grid">
        <article className="stat-card sage"><div className="stat-card-top"><span>In stock</span></div><div className="stat-value">{total}</div><div className="stat-foot">{selected.unit}</div></article>
        <article className="stat-card blue"><div className="stat-card-top"><span>Batches</span></div><div className="stat-value">{batches.filter((row) => row.quantity > 0).length}</div><div className="stat-foot">with stock</div></article>
        <article className="stat-card amber"><div className="stat-card-top"><span>Price</span></div><div className="stat-value">₹{Number(selected.price).toFixed(2)}</div><div className="stat-foot">per unit</div></article>
        <article className="stat-card coral"><div className="stat-card-top"><span>Next expiry</span></div><div className="stat-value">{nearest.length ? `${Math.min(...nearest)}d` : '—'}</div><div className="stat-foot">days left</div></article>
      </section>
      <section className="panel data-panel">
        <div className="table-toolbar"><div><p className="eyebrow">Product details</p><h2>Where it is kept</h2></div></div>
        <div className="detail-list"><div><span>Aisle</span><strong>{selected.aisle || 'Unassigned'}</strong></div><div><span>Shelf</span><strong>{selected.shelf_number || 'Unassigned'}</strong></div><div><span>Section</span><strong>{selected.storage_section || selected.category}</strong></div><div><span>Units per box</span><strong>{selected.units_per_box}</strong></div></div>
      </section>
      <section className="panel data-panel">
        <div className="table-toolbar"><div><p className="eyebrow">Batches</p><h2>Stock by batch</h2></div></div>
        {batches.length ? <div className="data-table"><div className="data-head"><span>Batch</span><span>Quantity</span><span>Expiry</span><span>Location</span></div>{batches.map((row) => { const days = daysUntil(row.expiry_date); return <div className="data-row" key={row.inventory_id}><strong>{row.batch_number ?? `Batch ${row.batch_id}`}<small>Serial {row.serial_number ?? '—'}</small></strong><span>{row.quantity} {selected.unit}</span><span className={days !== null && days <= 7 ? 'warning-text' : ''}>{row.expiry_date ? `${new Date(row.expiry_date).toLocaleDateString()}${days !== null ? days < 0 ? ' · expired' : ` · ${days}d` : ''}` : '—'}</span><span>{row.location_code ?? 'Unassigned'}</span></div> })}</div> : <p className="field-hint">No batches have been received for this product yet.</p>}
      </section>
    </>
  }

  const query = search.trim().toLowerCase()
  const visible = products.filter((product) => !query || product.name.toLowerCase().includes(query) || (product.serial_number ?? '').toLowerCase().includes(query)).sort((a, b) => a.name.localeCompare(b.name))
  return <>
    <section className="module-header"><div><p className="eyebrow">Warehouse inventory</p><h1>Products</h1><p>Tap a product to see its batches, expiry dates and shelf location.</p></div></section>
    <label className="search-field"><Search size={18} /><input type="search" placeholder="Search by name or serial number" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
    {visible.length ? <section className="product-list">{visible.map((product) => {
      const units = unitsOf(product.product_id)
      const status = units <= 0 ? 'OUT' : units <= product.reorder_level ? 'LOW' : 'IN STOCK'
      return <button className="product-card" key={product.product_id} onClick={() => setSelectedId(product.product_id)}>
        <div><strong>{product.name}</strong><small>{product.serial_number ? `Serial ${product.serial_number}` : product.storage_section || product.category}</small></div>
        <div className="product-card-stock"><strong>{units}</strong><span className={`pill ${status === 'IN STOCK' ? 'ready' : 'urgent'}`}>{status}</span></div>
        <ChevronRight size={18} />
      </button>
    })}</section> : <div className="panel"><div className="empty-state"><strong>{products.length ? 'No matching products' : 'No products yet'}</strong><span>{products.length ? 'Try a different name or serial number.' : 'Products appear here after a worker receives an approved stock request.'}</span></div></div>}
  </>
}
