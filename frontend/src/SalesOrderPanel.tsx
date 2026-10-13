// @ts-nocheck
import { useState } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { approveOrder, cancelOrder, fulfillOrder, getOrders, rejectOrder, Role } from './api'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { role: Role; onToast: (message: string) => void }

export default function SalesOrderPanel({ role, onToast }: Props) {
  const [orders, setOrders] = useState<Awaited<ReturnType<typeof getOrders>>['orders']>([])
  const [error, setError] = useState('')

  const load = async () => {
    try {
      setOrders((await getOrders()).orders)
      setError('')
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Could not load orders')
    }
  }

  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading sales orders" />

  async function act(orderId: number, action: 'approve' | 'reject' | 'fulfill' | 'cancel') {
    try {
      if (action === 'approve') await approveOrder(orderId)
      if (action === 'reject') await rejectOrder(orderId)
      if (action === 'fulfill') await fulfillOrder(orderId)
      if (action === 'cancel') await cancelOrder(orderId)
      onToast(action === 'approve' ? 'Order approved and stock reserved' : action === 'reject' ? 'Order rejected' : action === 'cancel' ? 'Order cancelled and stock released' : 'Order fulfilled')
      await load()
    } catch (problem) {
      onToast(problem instanceof Error ? problem.message : 'Order action failed')
    }
  }

  return <><section className="module-header"><div><p className="eyebrow">Sales workflow</p><h1>Orders</h1><p>{role === 'manager' ? 'Create and approve orders for your warehouse.' : role === 'warehouse_worker' ? 'Fulfill approved orders for your warehouse.' : 'Track the approval and fulfillment status of your orders.'}</p></div><button className="button subtle" onClick={() => void load()}><RefreshCw size={16} /> Refresh</button></section>{error ? <div className="panel info-banner"><AlertTriangle size={18} /><div><strong>Orders unavailable</strong><span>{error}</span></div></div> : <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Warehouse queue</p><h2>{orders.length} orders</h2></div></div>{orders.length ? <div className="data-table"><div className="data-head"><span>Order</span><span>Products</span><span>Created</span><span>Status</span><span>Action</span></div>{orders.map((order) => <div className="data-row" key={order.order_id}><strong>#{order.order_id}</strong><span>{order.items?.length ? order.items.map((item) => `${item.product_name} x${item.quantity}`).join(', ') : 'No items'}</span><span>{new Date(order.created_at).toLocaleString()}</span><span className={`pill ${order.status === 'approved' || order.status === 'confirmed' ? 'ready' : order.status === 'rejected' ? 'urgent' : 'pending'}`}>{order.status === 'approved' && order.reservation_status === 'short' ? 'approved - stock short' : order.status}</span><span>{role === 'manager' && order.status === 'pending' && <><button className="row-action" onClick={() => void act(order.order_id, 'approve')}>Approve</button><button className="row-action danger" onClick={() => void act(order.order_id, 'reject')}>Reject</button></>}{role === 'manager' && order.status === 'approved' && <button className="row-action danger" onClick={() => void act(order.order_id, 'cancel')}>Cancel and release stock</button>}{role === 'warehouse_worker' && order.status === 'approved' && <button className="row-action" onClick={() => void act(order.order_id, 'fulfill')}>Fulfill</button>}</span></div>)}</div> : <div className="empty-state"><CheckCircle2 size={28} /><strong>No orders in your queue</strong><span>New warehouse orders will appear here.</span></div>}</section>}</>
}