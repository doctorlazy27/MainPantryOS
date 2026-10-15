import { FormEvent, useState } from 'react'
import { getDashboard, getExpiredInventory, getExpiringInventory, getInventory, getProducts, getTemperatureLogs, recordTemperature, updateBatchStatus, DashboardData, InventoryRecord, Product, Role, TemperatureLog } from './api'
import AppSelect from './AppSelect'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { role: Role; onToast: (message: string) => void }

export default function InventoryOverview({ role, onToast }: Props) {
  const [products, setProducts] = useState<Product[]>([])
  const [inventory, setInventory] = useState<InventoryRecord[]>([])
  const [expiring, setExpiring] = useState<Awaited<ReturnType<typeof getExpiringInventory>>['items']>([])
  const [expired, setExpired] = useState<Awaited<ReturnType<typeof getExpiredInventory>>['items']>([])
  const [intelligence, setIntelligence] = useState<DashboardData['inventory_intelligence']>([])
  const [lowStock, setLowStock] = useState<DashboardData['low_stock_products']>([])
  const [temperatureLogs, setTemperatureLogs] = useState<TemperatureLog[]>([])
  const [temperatureInputs, setTemperatureInputs] = useState<Record<number, string>>({})
  const [expiryFilter, setExpiryFilter] = useState<'all' | '7' | '3' | '1' | 'expired'>('all')
  const [sectionFilter, setSectionFilter] = useState('all')

  const load = async () => {
    try {
      const [productResult, inventoryResult, expiringResult, expiredResult, dashboard, temperatureResult] = await Promise.all([
        getProducts(), getInventory(), getExpiringInventory(), getExpiredInventory(), getDashboard(), getTemperatureLogs(),
      ])
      setProducts(productResult.products)
      setInventory(inventoryResult.inventory)
      setExpiring(expiringResult.items)
      setExpired(expiredResult.items)
      setIntelligence(dashboard.inventory_intelligence)
      setLowStock(dashboard.low_stock_products)
      setTemperatureLogs(temperatureResult.logs)
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Could not load inventory')
    }
  }

  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading warehouse inventory" />

  const rows = products.map((product) => {
    const records = inventory.filter((item) => item.product_id === product.product_id)
    const productExpiry = expiring.filter((item) => item.product_id === product.product_id)
    const stock = records.reduce((total, item) => total + item.quantity, 0)
    const boxes = records.reduce((total, item) => total + item.boxed_units, 0)
    const nearestDays = productExpiry.length ? Math.min(...productExpiry.map((item) => item.days_remaining)) : null
    return {
      product,
      stock,
      boxes,
      unitCost: records[0]?.unit_price ?? product.price,
      boxCost: records.reduce((total, item) => total + item.total_box_cost, 0),
      nearestDays,
      stockStatus: stock <= product.reorder_level ? 'LOW' : 'GOOD',
    }
  })
  const sections = [...new Set(rows.map(({ product }) => product.storage_section || product.category))]
  const visibleRows = sectionFilter === 'all' ? rows : rows.filter(({ product }) => (product.storage_section || product.category) === sectionFilter)
  const visibleExpiring = expiryFilter === 'expired'
    ? []
    : expiring.filter((item) => expiryFilter === 'all' || item.days_remaining <= Number(expiryFilter))

  async function setLotStatus(item: InventoryRecord, status: 'active' | 'quarantined' | 'disposed' | 'donated') {
    const reason = status === 'active' ? 'Manager released batch after QC review' : status === 'disposed' ? 'Manager approved batch disposal' : status === 'donated' ? 'Manager approved donation before expiry' : 'Manager placed batch on quality hold'
    try { await updateBatchStatus(item.batch_id, status, reason); onToast(`Batch ${item.batch_number ?? item.batch_id} marked ${status}`); await load() }
    catch (error) { onToast(error instanceof Error ? error.message : 'Could not update batch status') }
  }

  async function submitTemperature(item: InventoryRecord) {
    const reading = Number(temperatureInputs[item.batch_id])
    if (!Number.isFinite(reading)) { onToast('Enter a valid temperature in Celsius'); return }
    try {
      const result = await recordTemperature(item.batch_id, reading)
      onToast(result.within_range ? `Batch ${item.batch_number ?? item.batch_id} temperature is in range` : `Batch ${item.batch_number ?? item.batch_id} quarantined for temperature exception`)
      setTemperatureInputs({ ...temperatureInputs, [item.batch_id]: '' })
      await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not record temperature') }
  }

  return <>
    {role === 'warehouse_worker' && <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Cold-chain checks</p><h2>Record storage temperature</h2></div></div>{inventory.filter((item) => item.quantity > 0 && item.batch_status === 'active').map((item) => <form className="data-row compact" key={item.batch_id} onSubmit={(event) => { event.preventDefault(); void submitTemperature(item) }}><strong>{products.find((product) => product.product_id === item.product_id)?.name ?? `Product ${item.product_id}`} · {item.batch_number ?? `Batch ${item.batch_id}`}</strong><span>{item.storage_zone} · {item.location_code}</span><label>Temperature (C)<input type="number" step="0.1" required value={temperatureInputs[item.batch_id] ?? ''} onChange={(event) => setTemperatureInputs({ ...temperatureInputs, [item.batch_id]: event.target.value })} /></label><button className="row-action" type="submit">Record check</button></form>)}</section>}
    {role === 'manager' && <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Waste prevention</p><h2>Donation candidates</h2></div></div>{visibleExpiring.length ? visibleExpiring.map((item) => { const inventoryItem = inventory.find((record) => record.inventory_id === item.inventory_id); return <div className="data-row compact" key={item.inventory_id}><strong>{item.product_name} · {item.batch_number}</strong><span>{item.quantity} units</span><span>Expires in {item.days_remaining} days</span>{inventoryItem && inventoryItem.batch_status === 'active' && <button className="row-action" onClick={() => void setLotStatus(inventoryItem, 'donated')}>Record donation</button>}</div> }) : <p className="field-hint">No batches are approaching expiry within the selected window.</p>}</section>}
    <section className="panel low-stock-panel"><div className="table-toolbar"><div><p className="eyebrow">Replenishment queue</p><h2>Low stock</h2></div><span className="table-count">{lowStock.length} products need attention</span></div>{lowStock.length ? <div className="low-stock-list">{lowStock.map((item) => <div className="low-stock-item" key={item.product_id}><div><strong>{item.name}</strong><span>{item.current_quantity} {item.unit} available · reorder at {item.reorder_level}</span></div><span className="pill urgent">REFILL</span></div>)}</div> : <p className="field-hint">All tracked products are above their reorder level.</p>}</section>
    <section className="panel data-panel">
      <div className="table-toolbar"><div><p className="eyebrow">Warehouse inventory</p><h2>Food sections</h2></div><div className="module-actions"><AppSelect value={sectionFilter} onChange={(event) => setSectionFilter(event.target.value)} aria-label="Filter inventory section"><option value="all">All sections</option>{sections.map((section) => <option key={section} value={section}>{section}</option>)}</AppSelect><button className="button subtle" onClick={() => void load()}>Refresh</button></div></div>
      {role === 'warehouse_worker' && <p className="field-hint">Stock is grouped by food section. Submit an inventory request below to add boxed units.</p>}
      {visibleRows.length ? <div className="inventory-sections">{sections.filter((section) => sectionFilter === 'all' || section === sectionFilter).map((section) => <section className="inventory-section" key={section}>
        <h3>{section}</h3>
        <div className="data-table"><div className="data-head"><span>Product</span><span>Aisle</span><span>Shelf</span><span>Units</span><span>Boxed units</span><span>Stock</span><span>Expiry</span><span>Per-unit cost</span><span>Total box cost</span><span>Serial number</span></div>
          {visibleRows.filter(({ product }) => (product.storage_section || product.category) === section).sort((left, right) => `${left.product.aisle} ${left.product.shelf_number} ${left.product.name}`.localeCompare(`${right.product.aisle} ${right.product.shelf_number} ${right.product.name}`)).map(({ product, stock, boxes, unitCost, boxCost, nearestDays, stockStatus }) => <div className="data-row" key={product.product_id}>
            <strong>{product.name}</strong><span>{product.aisle || 'Unassigned'}</span><span>{product.shelf_number || 'Unassigned'}</span><span>{stock} {product.unit}</span><span>{boxes}</span><span>{stockStatus}</span><span>{nearestDays === null ? 'ACTIVE' : `${nearestDays} days`}</span><span>${Number(unitCost).toFixed(2)}</span><span>${Number(boxCost).toFixed(2)}</span><span>{product.serial_number ?? 'Not registered'}</span>
          </div>)}
        </div>
      </section>)}</div> : <p className="field-hint">No products have been added yet.</p>}
    </section>

    <section className="panel data-panel">
      <div className="table-toolbar"><div><p className="eyebrow">Registered stock</p><h2>Batches by serial number</h2></div></div>
      {inventory.some((item) => item.quantity > 0) ? <div className="data-table"><div className="data-head"><span>Product</span><span>Serial number</span><span>Batch</span><span>Quantity</span><span>Location</span></div>{inventory.filter((item) => item.quantity > 0).map((item) => <div className="data-row" key={item.inventory_id}><strong>{products.find((product) => product.product_id === item.product_id)?.name ?? `Product ${item.product_id}`}</strong><span>{item.serial_number ?? 'Not registered'}</span><span>{item.batch_number ?? `Batch ${item.batch_id}`}</span><span>{item.quantity}</span><span>{item.location_code ?? 'Unassigned'}</span></div>)}</div> : <p className="field-hint">No stock has been registered yet.</p>}
    </section>

    <section className="panel data-panel">
      <div className="table-toolbar"><div><p className="eyebrow">Expiry intelligence</p><h2>Priority batches</h2></div></div>
      <div className="module-actions"><button className="button subtle" onClick={() => setExpiryFilter('all')}>7 days</button><button className="button subtle" onClick={() => setExpiryFilter('3')}>3 days</button><button className="button subtle" onClick={() => setExpiryFilter('1')}>Tomorrow</button><button className="button subtle" onClick={() => setExpiryFilter('expired')}>Expired</button></div>
      {expiryFilter === 'expired' ? expired.length ? <div className="data-table"><div className="data-head"><span>Product</span><span>Batch</span><span>Status</span><span>Historical units</span><span>Estimated value</span></div>{expired.map((item) => <div className="data-row" key={item.inventory_id}><strong>{item.product_name}</strong><span>{item.batch_number}</span><span className="warning-text">EXPIRED</span><span>{item.quantity}</span><span>${Number(item.estimated_value).toFixed(2)}</span></div>)}</div> : <p className="field-hint">No expired stock is recorded.</p> : visibleExpiring.length ? <div className="data-table"><div className="data-head"><span>Product</span><span>Batch</span><span>Status</span><span>Days remaining</span><span>Units</span><span>Estimated value</span><span>Action</span></div>{visibleExpiring.map((item) => <div className="data-row" key={item.inventory_id}><strong>{item.product_name}</strong><span>{item.batch_number}</span><span className={item.status === 'URGENT' ? 'warning-text' : ''}>{item.status}</span><span>{item.days_remaining}</span><span>{item.quantity}</span><span>${Number(item.estimated_value).toFixed(2)}</span><span>Prioritize FEFO</span></div>)}</div> : <p className="field-hint">No active batches match this expiry filter.</p>}
    </section>

    <section className="panel data-panel">
      <div className="table-toolbar"><div><p className="eyebrow">Smart inventory</p><h2>Risk and reorder suggestions</h2></div></div>
      {intelligence.length ? <div className="data-table"><div className="data-head"><span>Product</span><span>Stock</span><span>Demand/day</span><span>Stockout risk</span><span>Waste risk</span><span>Recommendation</span></div>{intelligence.map((item) => <div className="data-row" key={item.product_id}><strong>{item.product_name}</strong><span>{item.current_stock}</span><span>{item.average_daily_demand}</span><span className={item.stockout_risk === 'HIGH' ? 'warning-text' : ''}>{item.stockout_risk}{item.estimated_days_remaining === null ? '' : ` · ${item.estimated_days_remaining} days`}</span><span className={item.waste_risk === 'HIGH' ? 'warning-text' : ''}>{item.waste_risk}</span><span>{item.recommendation}{item.recommended_reorder > 0 ? ` · Suggested reorder: ${item.recommended_reorder}` : ''}</span></div>)}</div> : <p className="field-hint">Smart recommendations will appear as order and inventory history accumulates.</p>}
    </section>
    <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Cold-chain monitoring</p><h2>Recent temperature readings</h2></div></div>{temperatureLogs.length ? <div className="data-table"><div className="data-head"><span>Batch</span><span>Zone</span><span>Reading</span><span>Allowed range</span><span>Stage</span><span>Recorded</span></div>{temperatureLogs.slice(0, 12).map((log) => <div className="data-row" key={log.temperature_log_id}><strong>#{log.batch_id}</strong><span>{log.storage_zone}</span><span className={log.within_range ? '' : 'warning-text'}>{log.temperature_c} C · {log.within_range ? 'OK' : 'OUT OF RANGE'}</span><span>{log.minimum_c} to {log.maximum_c ?? 'no max'} C</span><span>{log.stage}</span><span>{new Date(log.recorded_at).toLocaleString()}</span></div>)}</div> : <p className="field-hint">No temperature readings have been recorded.</p>}</section>
    {role === 'manager' && <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Quality control</p><h2>Quarantine and disposal</h2></div></div>{inventory.filter((item) => item.batch_status === 'quarantined' || item.batch_status === 'active').length ? inventory.filter((item) => item.batch_status === 'quarantined' || item.batch_status === 'active').map((item) => <div className="data-row compact" key={item.inventory_id}><strong>{item.batch_number ?? `Batch ${item.batch_id}`}</strong><span>{products.find((product) => product.product_id === item.product_id)?.name ?? `Product ${item.product_id}`}</span><span>{item.quantity} units · {item.batch_status}</span><span>{item.location_code ?? 'Unassigned'}</span>{item.batch_status === 'quarantined' && <button className="row-action" onClick={() => void setLotStatus(item, 'active')}>Release to putaway</button>}{item.batch_status === 'active' && <button className="row-action" onClick={() => void setLotStatus(item, 'quarantined')}>Quarantine</button>}<button className="row-action danger" onClick={() => void setLotStatus(item, 'disposed')}>Dispose</button></div>) : <p className="field-hint">No active or quarantined lots need a quality decision.</p>}</section>}
  </>
}
