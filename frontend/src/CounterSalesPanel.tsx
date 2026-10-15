import { useState } from 'react'
import { CounterSale, getCounterSales } from './api'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { onToast: (message: string) => void }

export default function CounterSalesPanel({ onToast }: Props) {
  const [sales, setSales] = useState<CounterSale[]>([])
  async function load() {
    try { setSales((await getCounterSales()).sales) }
    catch (error) { onToast(error instanceof Error ? error.message : 'Could not load counter invoices') }
  }
  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading counter invoices" />
  const total = sales.reduce((sum, sale) => sum + sale.total_amount, 0)

  return <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Checkout counter</p><h2>Counter invoices</h2></div><span className="table-count">{sales.length} sales · ₹{total.toFixed(2)}</span><button className="button subtle" onClick={() => void load()}>Refresh</button></div>{sales.length ? sales.map((sale) => <details className="invoice-detail" key={sale.sale_id}><summary className="data-row compact"><strong>{sale.bill_number}</strong><span>{sale.cashier_name ?? 'Cashier'}</span><span>{new Date(sale.created_at.endsWith('Z') ? sale.created_at : `${sale.created_at}Z`).toLocaleString()}</span><strong>₹{sale.total_amount.toFixed(2)}</strong></summary><div className="data-table"><div className="data-head"><span>Product</span><span>Serial</span><span>Qty</span><span>Line total</span></div>{sale.items.map((line) => <div className="data-row" key={`${sale.sale_id}-${line.product_id}`}><strong>{line.product_name}</strong><span>{line.serial_number ?? '—'}</span><span>{line.quantity} × ₹{line.unit_price.toFixed(2)}</span><span>₹{line.line_total.toFixed(2)}</span></div>)}</div></details>) : <p className="field-hint">No checkout sales have been recorded yet.</p>}</section>
}
