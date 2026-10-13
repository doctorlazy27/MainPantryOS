import { FormEvent, useState } from 'react'
import { approveInventoryAddition, createInventoryAdditionRequest, getInventoryAdditionRequests, rejectInventoryAddition, Role } from './api'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'
import AppSelect from './AppSelect'

type Props = { role: Role; onToast: (message: string) => void }
type RequestRow = Awaited<ReturnType<typeof getInventoryAdditionRequests>>['requests'][number]
type FillForm = { product_name: string; category: string; units_per_box: string; boxed_units: string; unit_price: string; box_unit_cost: string; scanned_code: string }
type ApprovalForm = { batch_number: string; manufacturing_date: string; expiry_date: string; storage_zone: 'AMBIENT' | 'CHILLED' | 'FROZEN'; temperature_c: string; aisle: string; shelf_number: string }
const categories = ['Fruits', 'Vegetables', 'Boxed items', 'Ready made items', 'Raw meat items', 'Poultry', 'Dairy', 'Frozen items', 'Other']
const emptyFill: FillForm = { product_name: '', category: 'Fruits', units_per_box: '1', boxed_units: '0', unit_price: '', box_unit_cost: '', scanned_code: '' }
const emptyApproval: ApprovalForm = { batch_number: '', manufacturing_date: '', expiry_date: '', storage_zone: 'AMBIENT', temperature_c: '20', aisle: '', shelf_number: '' }

export default function InventoryRequestsPanel({ role, onToast }: Props) {
  const [requests, setRequests] = useState<RequestRow[]>([])
  const [form, setForm] = useState<FillForm>(emptyFill)
  const [approvalId, setApprovalId] = useState<number | null>(null)
  const [approval, setApproval] = useState<ApprovalForm>(emptyApproval)

  async function load() {
    try { setRequests((await getInventoryAdditionRequests()).requests) }
    catch (error) { onToast(error instanceof Error ? error.message : 'Could not load inventory requests') }
  }

  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading inventory requests" />

  async function submit(event: FormEvent) {
    event.preventDefault()
    const unitsPerBox = Number(form.units_per_box); const boxedUnits = Number(form.boxed_units); const unitPrice = Number(form.unit_price); const boxCost = form.box_unit_cost ? Number(form.box_unit_cost) : unitPrice * unitsPerBox
    if (!form.product_name.trim() || unitsPerBox < 1 || boxedUnits < 1 || !Number.isFinite(unitPrice) || unitPrice < 0) { onToast('Enter a valid product, quantity, units per box, and price'); return }
    try { await createInventoryAdditionRequest({ product_name: form.product_name.trim(), category: form.category, quantity: boxedUnits * unitsPerBox, units_per_box: unitsPerBox, boxed_units: boxedUnits, unit_price: unitPrice, box_unit_cost: boxCost, scanned_codes: form.scanned_code ? [form.scanned_code] : [] }); onToast('Inventory fill request sent to manager'); setForm(emptyFill); await load() }
    catch (error) { onToast(error instanceof Error ? error.message : 'Could not submit inventory request') }
  }

  async function review(id: number, approve: boolean) {
    try {
      if (approve) { await approveInventoryAddition(id, approval); setApprovalId(null); setApproval(emptyApproval) }
      else await rejectInventoryAddition(id)
      onToast(approve ? 'Inventory request approved and batched' : 'Inventory request rejected'); await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not review inventory request') }
  }

  const pending = requests.filter((item) => item.status === 'pending')
  return <>
    {role === 'warehouse_worker' && <section className="panel workflow-card"><p className="eyebrow">Warehouse fill request</p><h2>Request stock to receive</h2><p>Submit the product and quantity. A manager assigns the batch and physical location after approval.</p><form className="stack-form" onSubmit={submit}><label>Product name<input required placeholder="Enter product" value={form.product_name} onChange={(event) => setForm({ ...form, product_name: event.target.value })} /></label><label>Food section<AppSelect value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })}>{categories.map((category) => <option key={category}>{category}</option>)}</AppSelect></label><label>Units per box<input required type="number" min="1" value={form.units_per_box} onChange={(event) => setForm({ ...form, units_per_box: event.target.value })} /></label><label>Boxed units<input required type="number" min="1" value={form.boxed_units} onChange={(event) => setForm({ ...form, boxed_units: event.target.value })} /></label><label>Total individual units<input readOnly value={Number(form.units_per_box || 0) * Number(form.boxed_units || 0)} /></label><label>Price per unit<input required type="number" min="0" step="0.01" value={form.unit_price} onChange={(event) => setForm({ ...form, unit_price: event.target.value })} /></label><label>Total cost per box<input type="number" min="0" step="0.01" value={form.box_unit_cost} onChange={(event) => setForm({ ...form, box_unit_cost: event.target.value })} /></label><label>Boxed-unit code<input placeholder="Optional barcode" value={form.scanned_code} onChange={(event) => setForm({ ...form, scanned_code: event.target.value })} /></label><button className="button primary" type="submit">Send manager request</button></form></section>}
    {role === 'manager' && <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Inventory approvals</p><h2>{pending.length} pending requests</h2></div><button className="button subtle" onClick={() => void load()}>Refresh</button></div>{pending.length ? pending.map((item) => <div className="data-row compact" key={item.request_id}><strong>Request #{item.request_id}</strong><span>{item.product_name}</span><span>{item.quantity} units · {item.boxed_units} boxes</span><button className="row-action" onClick={() => { setApprovalId(item.request_id); setApproval(emptyApproval) }}>Batch and approve</button><button className="row-action danger" onClick={() => void review(item.request_id, false)}>Reject</button></div>) : <div className="empty-state"><strong>No pending inventory fills</strong><span>Worker stock requests will appear here.</span></div>}</section>}
    {approvalId !== null && <div className="modal-backdrop" onMouseDown={() => setApprovalId(null)}><div className="modal" onMouseDown={(event) => event.stopPropagation()}><div className="modal-header"><div><p className="eyebrow">Manager approval</p><h2>QC, batch, and putaway</h2></div></div><form className="form-grid" onSubmit={(event) => { event.preventDefault(); void review(approvalId, true) }}><label>Batch number<input required value={approval.batch_number} onChange={(event) => setApproval({ ...approval, batch_number: event.target.value })} /></label><label>Manufacturing date<input required type="date" value={approval.manufacturing_date} onChange={(event) => setApproval({ ...approval, manufacturing_date: event.target.value })} /></label><label>Expiry date<input required type="date" value={approval.expiry_date} onChange={(event) => setApproval({ ...approval, expiry_date: event.target.value })} /></label><label>Storage zone<AppSelect value={approval.storage_zone} onChange={(event) => setApproval({ ...approval, storage_zone: event.target.value as ApprovalForm['storage_zone'] })}><option value="AMBIENT">Ambient</option><option value="CHILLED">Chilled</option><option value="FROZEN">Frozen</option></AppSelect></label><label>Receiving temperature (C)<input required type="number" step="0.1" value={approval.temperature_c} onChange={(event) => setApproval({ ...approval, temperature_c: event.target.value })} /></label><label>Aisle<input required placeholder="Aisle A" value={approval.aisle} onChange={(event) => setApproval({ ...approval, aisle: event.target.value })} /></label><label>Shelf number<input required placeholder="A-03" value={approval.shelf_number} onChange={(event) => setApproval({ ...approval, shelf_number: event.target.value })} /></label><div className="form-actions"><button className="button subtle" type="button" onClick={() => setApprovalId(null)}>Cancel</button><button className="button primary" type="submit">Approve and receive</button></div></form></div></div>}
  </>
}