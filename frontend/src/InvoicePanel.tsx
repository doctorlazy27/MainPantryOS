// @ts-nocheck
import { useEffect, useState } from 'react'
import { FileText, RefreshCw, Sparkles } from 'lucide-react'
import { confirmInvoice, getInvoiceReport, getInvoices, Invoice, InvoiceReport, InvoiceReportPeriod, Role, summarizeInvoiceReport } from './api'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { role: Role; onToast: (message: string) => void }
const periods: InvoiceReportPeriod[] = ['weekly', 'monthly', 'yearly']

export default function InvoicePanel({ role, onToast }: Props) {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [period, setPeriod] = useState<InvoiceReportPeriod>('weekly')
  const [report, setReport] = useState<InvoiceReport | null>(null)
  const [summary, setSummary] = useState('')
  const [summaryPowered, setSummaryPowered] = useState(false)
  const [reportError, setReportError] = useState('')
  const [loadingSummary, setLoadingSummary] = useState(false)

  async function loadInvoices() {
    try {
      setInvoices((await getInvoices()).invoices)
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Could not load invoices')
    }
  }

  async function loadReport(selectedPeriod: InvoiceReportPeriod) {
    try {
      setReport(await getInvoiceReport(selectedPeriod))
      setReportError('')
    } catch (error) {
      setReport(null)
      setReportError(error instanceof Error ? error.message : 'Could not load invoice report')
    }
  }

  const { initialLoading } = useLiveRefresh(loadInvoices)
  useEffect(() => { setSummary(''); void loadReport(period) }, [period])

  async function refresh() {
    await Promise.all([loadInvoices(), loadReport(period)])
  }

  async function runAction(invoice: Invoice) {
    try {
      await confirmInvoice(invoice.invoice_id)
      onToast('Invoice confirmed')
      await refresh()
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Invoice action failed')
    }
  }

  async function makeSummary() {
    setLoadingSummary(true)
    try {
      const result = await summarizeInvoiceReport(period)
      setSummary(result.summary)
      setSummaryPowered(result.ai_powered)
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Could not summarize this report')
    } finally {
      setLoadingSummary(false)
    }
  }
    if (initialLoading) return <LoadingState label="Loading invoices" />

  return <><section className="module-header"><div><p className="eyebrow">Billing and analytics</p><h1>Invoices</h1><p>Review invoices and summarize issued amounts for your warehouse.</p></div><button className="button subtle" onClick={() => void refresh()}><RefreshCw size={16} /> Refresh</button></section><section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Invoice activity</p><h2>Generation report</h2></div><div className="auth-tabs" role="tablist" aria-label="Invoice report period">{periods.map((item) => <button key={item} role="tab" aria-selected={period === item} className={period === item ? 'active' : ''} onClick={() => setPeriod(item)}>{item[0].toUpperCase() + item.slice(1)}</button>)}</div></div>{reportError ? <div className="field-hint">{reportError}</div> : report && <><div className="stat-grid"><article className="stat-card sage"><div className="stat-card-top"><span>Invoices</span><div className="stat-icon"><FileText size={18} /></div></div><div className="stat-value">{report.invoice_count.toLocaleString()}</div><div className="stat-foot">{report.starts_on} to {report.ends_on}</div></article><article className="stat-card blue"><div className="stat-card-top"><span>Total issued</span><div className="stat-icon"><FileText size={18} /></div></div><div className="stat-value">${report.total_amount.toFixed(2)}</div><div className="stat-foot">Calendar {report.period} total</div></article><article className="stat-card amber"><div className="stat-card-top"><span>Previous period</span><div className="stat-icon"><RefreshCw size={18} /></div></div><div className="stat-value">${report.previous_period.total_amount.toFixed(2)}</div><div className="stat-foot">{report.change_percent === null ? 'No previous-period amount' : `${report.change_percent > 0 ? '+' : ''}${report.change_percent}% vs previous period`}</div></article></div><div className="report-status-row">{Object.entries(report.by_status).map(([status, values]) => <span className="pill pending" key={status}>{status}: {values.count} · ${values.amount.toFixed(2)}</span>)}</div><div className="copilot-ask"><button className="button primary" disabled={loadingSummary} onClick={() => void makeSummary()}><Sparkles size={16} />{loadingSummary ? 'Summarizing...' : 'Generate AI summary'}</button></div>{summary && <div className="copilot-answer"><span>{summaryPowered ? 'AI model summary' : 'Local summary · AI not configured or unavailable'}</span><strong>{summary}</strong></div>}</>}</section><section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Invoice register</p><h2>{invoices.length} invoices</h2></div></div>{invoices.length ? <div className="data-table"><div className="data-head"><span>Invoice</span><span>Order</span><span>Created</span><span>Total</span><span>Status</span><span>Action</span></div>{invoices.map((invoice) => <div className="data-row" key={invoice.invoice_id}><strong>#{invoice.invoice_id}</strong><span>#{invoice.order_id}</span><span>{invoice.created_at ? new Date(invoice.created_at).toLocaleDateString() : '—'}</span><span>${Number(invoice.total_amount).toFixed(2)}</span><span className="pill ready">{invoice.status}</span><span>{role === 'manager' && invoice.status === 'sent' && <button className="row-action" onClick={() => void runAction(invoice)}>Confirm</button>}</span></div>)}</div> : <div className="empty-state"><FileText size={28} /><strong>No invoices</strong><span>Invoices appear after a manager confirms an order receipt.</span></div>}</section></>
}