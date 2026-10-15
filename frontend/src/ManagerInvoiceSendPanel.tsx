import { useState } from 'react'
import { FileText, RefreshCw } from 'lucide-react'
import { getInvoices, Invoice, sendInvoice } from './api'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { onToast: (message: string) => void }

export default function ManagerInvoiceSendPanel({ onToast }: Props) {
  const [invoices, setInvoices] = useState<Invoice[]>([])

  const load = async () => {
    try {
      setInvoices((await getInvoices()).invoices.filter((invoice) => invoice.status === 'generated'))
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Could not load generated invoices')
    }
  }

  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading generated invoices" />

  async function send(invoiceId: number) {
    try {
      await sendInvoice(invoiceId)
      onToast(`Invoice #${invoiceId} sent for confirmation`)
      await load()
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Could not send invoice')
    }
  }

  return <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Invoice workflow</p><h2>Generated invoices awaiting send</h2></div><button className="button subtle" onClick={() => void load()}><RefreshCw size={16} /> Refresh</button></div>{invoices.length ? invoices.map((invoice) => <div className="data-row compact" key={invoice.invoice_id}><strong>Invoice #{invoice.invoice_id}</strong><span>Order #{invoice.order_id}</span><span>₹{Number(invoice.total_amount).toFixed(2)}</span><button className="row-action" onClick={() => void send(invoice.invoice_id)}>Send invoice</button></div>) : <div className="empty-state"><FileText size={26} /><strong>No generated invoices waiting</strong><span>Invoices generated from delivered orders will appear here.</span></div>}</section>
}