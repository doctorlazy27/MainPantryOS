// @ts-nocheck
import { FormEvent, useState } from 'react'
import { approveWarehouseRequest, getProducts, getWarehouseRequests, Product, rejectWarehouseRequest, requestWarehouseStock, Role } from './api'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'
import AppSelect from './AppSelect'

type Props = { role: Role; onToast: (message: string) => void }

export default function StockRequestPanel({ role, onToast }: Props) {
  const [products, setProducts] = useState<Product[]>([])
  const [requests, setRequests] = useState<Awaited<ReturnType<typeof getWarehouseRequests>>['requests']>([])
  const [product, setProduct] = useState('')
  const [quantity, setQuantity] = useState('')
  const load = async () => { try { const [productData, requestData] = await Promise.all([getProducts(), getWarehouseRequests()]); setProducts(productData.products); setRequests(requestData.requests) } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load stock requests') } }
  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading warehouse requests" />
  async function submit(event: FormEvent) { event.preventDefault(); const amount = Number(quantity); if (!Number.isFinite(amount) || amount < 1) { onToast('Enter a valid quantity'); return } try { await requestWarehouseStock({ product_id: Number(product), quantity: amount }); onToast('Stock request sent to the warehouse'); setQuantity(''); await load() } catch (error) { onToast(error instanceof Error ? error.message : 'Could not request stock') } }
  async function review(id: number, approve: boolean) { try { if (approve) await approveWarehouseRequest(id); else await rejectWarehouseRequest(id); onToast(approve ? 'Stock moved to counter' : 'Stock request rejected'); await load() } catch (error) { onToast(error instanceof Error ? error.message : 'Could not review stock request') } }
  return <>{role === 'manager' && <section className="panel workflow-card"><p className="eyebrow">Warehouse stock</p><h2>Request products for sale</h2><form className="form-grid" onSubmit={submit}><label>Product<AppSelect required value={product} onChange={(event) => setProduct(event.target.value)}><option value="">Select product</option>{products.map((item) => <option key={item.product_id} value={item.product_id}>{item.name}</option>)}</AppSelect></label><label>Quantity<input required type="number" min="1" placeholder="Enter quantity" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label><button className="button primary" type="submit">Send to warehouse</button></form></section>}{role === 'warehouse_worker' && <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Warehouse requests</p><h2>Requests waiting for fulfillment</h2></div><button className="button subtle" onClick={() => void load()}>Refresh</button></div>{requests.filter((item) => item.status === 'pending').map((item) => <div className="data-row compact" key={item.request_id}><strong>Request #{item.request_id}</strong><span>{item.product_name}</span><span>{item.quantity} units</span><button className="row-action" onClick={() => void review(item.request_id, true)}>Move to counter</button><button className="row-action danger" onClick={() => void review(item.request_id, false)}>Reject</button></div>)}</section>}</>
}
