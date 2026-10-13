import { useState } from 'react'
import { getInventoryRecommendations, getSuppliers, InventoryRecommendation, reviewInventoryRecommendation, Supplier } from './api'
import AppSelect from './AppSelect'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { onToast: (message: string) => void }

export default function ReorderPanel({ onToast }: Props) {
  const [recommendations, setRecommendations] = useState<InventoryRecommendation[]>([])
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [supplierIds, setSupplierIds] = useState<Record<number, string>>({})
  const load = async () => {
    try {
      const [recommendationData, supplierData] = await Promise.all([getInventoryRecommendations(), getSuppliers()])
      setRecommendations(recommendationData.recommendations)
      setSuppliers(supplierData.suppliers)
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load reorder recommendations') }
  }
  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading reorder recommendations" />

  async function decide(item: InventoryRecommendation, decision: 'approve' | 'reject') {
    const supplierId = Number(supplierIds[item.recommendation_id])
    if (decision === 'approve' && !supplierId) { onToast('Choose a supplier before approving the reorder'); return }
    try {
      const result = await reviewInventoryRecommendation(item.recommendation_id, decision, decision === 'approve' ? supplierId : undefined)
      onToast(decision === 'approve' ? `Purchase order #${result.purchase_order_id} created for ${item.product_name}` : `Reorder recommendation for ${item.product_name} rejected`)
      await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not review recommendation') }
  }

  const pending = recommendations.filter((item) => item.status === 'PENDING')
  return <><section className="module-header"><div><p className="eyebrow">Demand planning</p><h1>Reorder recommendations</h1><p>Review stock-risk calculations, choose a supplier, and create an inbound purchase order.</p></div><button className="button subtle" onClick={() => void load()}>Refresh</button></section><section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Manager review</p><h2>{pending.length} awaiting decision</h2></div></div>{pending.length ? <div className="data-table"><div className="data-head"><span>Product</span><span>Current stock</span><span>Demand/day</span><span>Suggested qty</span><span>Reason</span><span>Supplier</span><span>Action</span></div>{pending.map((item) => <div className="data-row" key={item.recommendation_id}><strong>{item.product_name}</strong><span>{item.current_stock}</span><span>{item.average_daily_demand}</span><span>{item.recommended_quantity}</span><span>{item.reason}</span><span><AppSelect aria-label={`Supplier for ${item.product_name}`} value={supplierIds[item.recommendation_id] ?? ''} onChange={(event) => setSupplierIds({ ...supplierIds, [item.recommendation_id]: event.target.value })}><option value="">Select supplier</option>{suppliers.map((supplier) => <option key={supplier.supplier_id} value={supplier.supplier_id}>{supplier.name}</option>)}</AppSelect></span><span className="review-actions"><button className="row-action" onClick={() => void decide(item, 'approve')}>Approve & create PO</button><button className="row-action danger" onClick={() => void decide(item, 'reject')}>Reject</button></span></div>)}</div> : <p className="field-hint">No pending reorder recommendations. New reviews appear as inventory and sales history update.</p>}</section><section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Review history</p><h2>Processed recommendations</h2></div></div>{recommendations.some((item) => item.status !== 'PENDING') ? <div className="data-table"><div className="data-head"><span>Product</span><span>Suggested quantity</span><span>Status</span><span>Reason</span></div>{recommendations.filter((item) => item.status !== 'PENDING').map((item) => <div className="data-row" key={item.recommendation_id}><strong>{item.product_name}</strong><span>{item.recommended_quantity}</span><span>{item.status}</span><span>{item.reason}</span></div>)}</div> : <p className="field-hint">No reviewed recommendations yet.</p>}</section></>
}