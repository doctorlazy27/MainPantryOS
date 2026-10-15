import { FormEvent, useState } from 'react'
import { Copy, UserPlus } from 'lucide-react'
import { Cashier, createCashier, deleteCashier, getCashiers } from './api'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { onToast: (message: string) => void }

export default function CounterAccountsPanel({ onToast }: Props) {
  const [cashiers, setCashiers] = useState<Cashier[]>([])
  const [name, setName] = useState('')
  const [customId, setCustomId] = useState('')
  const [created, setCreated] = useState<{ full_name: string; cashier_id: string } | null>(null)

  async function load() {
    try { setCashiers((await getCashiers()).cashiers) }
    catch (error) { onToast(error instanceof Error ? error.message : 'Could not load counter accounts') }
  }
  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading counter accounts" />

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (customId && !/^\d{10}$/.test(customId)) { onToast('A counter ID must be exactly 10 digits'); return }
    try {
      const result = await createCashier({ full_name: name.trim(), ...(customId ? { cashier_id: customId } : {}) })
      setCreated(result); setName(''); setCustomId(''); await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not create the counter account') }
  }

  async function remove(cashier: Cashier) {
    try { await deleteCashier(cashier.user_id); onToast(`${cashier.full_name} was removed`); await load() }
    catch (error) { onToast(error instanceof Error ? error.message : 'Could not remove the counter account') }
  }

  return <>
    <section className="module-header"><div><p className="eyebrow">Store access</p><h1>Counter accounts</h1><p>Create cashier accounts. A cashier signs in with the 10-digit ID you give them and can only use the checkout scanner.</p></div></section>
    <section className="panel workflow-card"><p className="eyebrow">New cashier</p><h2>Create a counter account</h2><form className="form-grid" onSubmit={(event) => void submit(event)}><label>Cashier name<input required value={name} onChange={(event) => setName(event.target.value)} /></label><label>10-digit ID (optional)<input inputMode="numeric" maxLength={10} pattern="\d{10}" placeholder="Leave blank to generate" value={customId} onChange={(event) => setCustomId(event.target.value.replace(/\D/g, ''))} /></label><button className="button primary" type="submit"><UserPlus size={16} /> Create account</button></form>{created && <div className="cashier-id-card"><span>{created.full_name}'s counter ID</span><strong>{created.cashier_id}</strong><button className="row-action" onClick={() => { void navigator.clipboard?.writeText(created.cashier_id); onToast('Counter ID copied') }}><Copy size={14} /> Copy</button></div>}</section>
    <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Counter accounts</p><h2>{cashiers.length} cashiers</h2></div></div>{cashiers.length ? <div className="data-table"><div className="data-head"><span>Name</span><span>Counter ID</span><span>Sales</span><span>Action</span></div>{cashiers.map((cashier) => <div className="data-row" key={cashier.user_id}><strong>{cashier.full_name}</strong><span>{cashier.cashier_id}</span><span>{cashier.sales_count}</span><button className="row-action danger" onClick={() => void remove(cashier)}>Remove</button></div>)}</div> : <p className="field-hint">No counter accounts yet.</p>}</section>
  </>
}
