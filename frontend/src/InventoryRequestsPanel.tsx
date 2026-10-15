import { FormEvent, useState } from 'react'
import { approveInventoryAddition, createInventoryAdditionRequest, getInventoryAdditionRequests, InventoryRequest, receiveInventoryAddition, rejectInventoryAddition, Role } from './api'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'
import AppSelect from './AppSelect'

type Props = { role: Role; onToast: (message: string) => void }
type FillForm = { product_name: string; category: string; units_per_box: string; boxed_units: string; unit_price: string; box_unit_cost: string }
type ReceiptForm = { serial_number: string; batch_number: string; manufacturing_date: string; expiry_date: string; storage_zone: 'AMBIENT' | 'CHILLED' | 'FROZEN'; temperature_c: string; aisle: string; shelf_number: string }
const categories = ['Fruits', 'Vegetables', 'Boxed items', 'Ready made items', 'Raw meat items', 'Poultry', 'Dairy', 'Frozen items', 'Other']
const emptyFill: FillForm = { product_name: '', category: 'Fruits', units_per_box: '1', boxed_units: '1', unit_price: '', box_unit_cost: '' }
const emptyReceipt: ReceiptForm = { serial_number: '', batch_number: '', manufacturing_date: '', expiry_date: '', storage_zone: 'AMBIENT', temperature_c: '20', aisle: '', shelf_number: '' }

export default function InventoryRequestsPanel({ role, onToast }: Props) {
  const [requests, setRequests] = useState<InventoryRequest[]>([])
  const [form, setForm] = useState<FillForm>(emptyFill)
  const [receivingId, setReceivingId] = useState<number | null>(null)
  const [receipt, setReceipt] = useState<ReceiptForm>(emptyReceipt)

  async function load() {
    try { setRequests((await getInventoryAdditionRequests()).requests) }
    catch (error) { onToast(error instanceof Error ? error.message : 'Could not load inventory requests') }
  }

  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading inventory requests" />

  async function submit(event: FormEvent) {
    event.preventDefault()
    const unitsPerBox = Number(form.units_per_box); const boxedUnits = Number(form.boxed_units); const unitPrice = Number(form.unit_price)
    const boxCost = form.box_unit_cost ? Number(form.box_unit_cost) : unitPrice * unitsPerBox
    if (!form.product_name.trim() || unitsPerBox < 1 || boxedUnits < 1 || !Number.isFinite(unitPrice) || unitPrice < 0) { onToast('Enter a valid product name, quantity, units per box, and price'); return }
    try {
      await createInventoryAdditionRequest({ product_name: form.product_name.trim(), category: form.category, quantity: boxedUnits * unitsPerBox, units_per_box: unitsPerBox, boxed_units: boxedUnits, unit_price: unitPrice, box_unit_cost: boxCost })
      onToast('Inventory request sent to the manager'); setForm(emptyFill); await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not submit inventory request') }
  }

  async function review(id: number, approve: boolean) {
    try {
      if (approve) await approveInventoryAddition(id); else await rejectInventoryAddition(id)
      onToast(approve ? 'Approved. The warehouse worker will record the delivery details.' : 'Request moved to rejected orders'); await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not review inventory request') }
  }

  async function confirmReceipt(event: FormEvent) {
    event.preventDefault()
    if (receivingId === null) return
    try {
      await receiveInventoryAddition(receivingId, { ...receipt, serial_number: receipt.serial_number.trim(), batch_number: receipt.batch_number.trim(), aisle: receipt.aisle.trim(), shelf_number: receipt.shelf_number.trim() })
      onToast('Product received and added to inventory'); setReceivingId(null); setReceipt(emptyReceipt); await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not record the received product') }
  }

  const pending = requests.filter((item) => item.status === 'pending')
  const approved = requests.filter((item) => item.status === 'approved')
  const received = requests.filter((item) => item.status === 'received').slice(0, 10)
  const rejected = requests.filter((item) => item.status === 'rejected')
  const summary = (item: InventoryRequest) => `${item.product_name} · ${item.quantity} units${item.boxed_units ? ` · ${item.boxed_units} boxes` : ''}`

  return <>
    {role === 'warehouse_worker' && <section className="panel workflow-card"><p className="eyebrow">Warehouse fill request</p><h2>Request stock to add</h2><p>Enter the product by name. After the manager approves, record the serial number, batch, dates, and shelf location once the delivery arrives.</p><form className="stack-form" onSubmit={submit}><label>Product name<input required placeholder="Enter product name" value={form.product_name} onChange={(event) => setForm({ ...form, product_name: event.target.value })} /></label><label>Food section<AppSelect value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })}>{categories.map((category) => <option key={category}>{category}</option>)}</AppSelect></label><label>Units per box<input required type="number" min="1" value={form.units_per_box} onChange={(event) => setForm({ ...form, units_per_box: event.target.value })} /></label><label>Boxed units<input required type="number" min="1" value={form.boxed_units} onChange={(event) => setForm({ ...form, boxed_units: event.target.value })} /></label><label>Total individual units<input readOnly value={Number(form.units_per_box || 0) * Number(form.boxed_units || 0)} /></label><label>Price per unit<input required type="number" min="0" step="0.01" value={form.unit_price} onChange={(event) => setForm({ ...form, unit_price: event.target.value })} /></label><label>Total cost per box<input type="number" min="0" step="0.01" value={form.box_unit_cost} onChange={(event) => setForm({ ...form, box_unit_cost: event.target.value })} /></label><button className="button primary" type="submit">Send manager request</button></form></section>}

    {role === 'manager' && <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Inventory approvals</p><h2>{pending.length} awaiting your decision</h2></div><button className="button subtle" onClick={() => void load()}>Refresh</button></div>{pending.length ? pending.map((item) => <div className="data-row compact" key={item.request_id}><strong>Request #{item.request_id}</strong><span>{summary(item)}</span><button className="row-action" onClick={() => void review(item.request_id, true)}>Approve</button><button className="row-action danger" onClick={() => void review(item.request_id, false)}>Reject</button></div>) : <div className="empty-state"><strong>No pending inventory requests</strong><span>Worker requests will appear here.</span></div>}</section>}

    <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">{role === 'warehouse_worker' ? 'Worker task' : 'Manager approved'}</p><h2>Approved, waiting for delivery details</h2></div></div>{approved.length ? approved.map((item) => <div className="data-row compact" key={item.request_id}><strong>Request #{item.request_id}</strong><span>{summary(item)}</span>{role === 'warehouse_worker' ? <button className="row-action" onClick={() => { setReceivingId(item.request_id); setReceipt(emptyReceipt) }}>Confirm received &amp; add details</button> : <span className="pill ready">Awaiting warehouse</span>}{role === 'manager' && <button className="row-action danger" onClick={() => void review(item.request_id, false)}>Reject</button>}</div>) : <p className="field-hint">No approved requests are waiting for the product to arrive.</p>}</section>

    {received.length > 0 && <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Recently added</p><h2>Registered in inventory</h2></div></div><div className="data-table"><div className="data-head"><span>Product</span><span>Serial number</span><span>Batch</span><span>Units</span></div>{received.map((item) => <div className="data-row" key={item.request_id}><strong>{item.product_name}</strong><span>{item.serial_number ?? '—'}</span><span>{item.batch_number ?? '—'}</span><span>{item.quantity}</span></div>)}</div></section>}

    <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Not added to inventory</p><h2>Rejected orders</h2></div><span className="table-count">{rejected.length}</span></div>{rejected.length ? rejected.map((item) => <div className="data-row compact" key={item.request_id}><strong>Request #{item.request_id}</strong><span>{summary(item)}</span><span className="pill urgent">REJECTED</span><span>{new Date(item.reviewed_at ?? item.created_at).toLocaleDateString()}</span></div>) : <p className="field-hint">No rejected inventory requests.</p>}</section>

    {receivingId !== null && <div className="modal-backdrop" onMouseDown={() => setReceivingId(null)}><div className="modal" onMouseDown={(event) => event.stopPropagation()}><div className="modal-header"><div><p className="eyebrow">Delivery received</p><h2>Serial, batch, and shelf details</h2></div></div><form className="form-grid" onSubmit={(event) => void confirmReceipt(event)}><label>Serial number (barcode)<input required autoFocus value={receipt.serial_number} onChange={(event) => setReceipt({ ...receipt, serial_number: event.target.value })} /></label><label>Batch number<input required value={receipt.batch_number} onChange={(event) => setReceipt({ ...receipt, batch_number: event.target.value })} /></label><label>Manufacturing date<input required type="date" value={receipt.manufacturing_date} onChange={(event) => setReceipt({ ...receipt, manufacturing_date: event.target.value })} /></label><label>Expiry date<input required type="date" value={receipt.expiry_date} onChange={(event) => setReceipt({ ...receipt, expiry_date: event.target.value })} /></label><label>Storage zone<AppSelect value={receipt.storage_zone} onChange={(event) => setReceipt({ ...receipt, storage_zone: event.target.value as ReceiptForm['storage_zone'] })}><option value="AMBIENT">Ambient</option><option value="CHILLED">Chilled</option><option value="FROZEN">Frozen</option></AppSelect></label><label>Receiving temperature (C)<input required type="number" step="0.1" value={receipt.temperature_c} onChange={(event) => setReceipt({ ...receipt, temperature_c: event.target.value })} /></label><label>Aisle<input required placeholder="Aisle A" value={receipt.aisle} onChange={(event) => setReceipt({ ...receipt, aisle: event.target.value })} /></label><label>Shelf number<input required placeholder="A-03" value={receipt.shelf_number} onChange={(event) => setReceipt({ ...receipt, shelf_number: event.target.value })} /></label><div className="form-actions"><button className="button subtle" type="button" onClick={() => setReceivingId(null)}>Cancel</button><button className="button primary" type="submit">Add to inventory</button></div></form></div></div>}
  </>
}
