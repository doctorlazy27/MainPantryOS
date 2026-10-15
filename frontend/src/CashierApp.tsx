import { FormEvent, useRef, useState } from 'react'
import { Barcode, Camera, LogOut, Minus, PackageCheck, Plus, ReceiptText, ScanLine, Trash2 } from 'lucide-react'
import { Capacitor } from '@capacitor/core'
import { BarcodeScanner } from '@capacitor-mlkit/barcode-scanning'
import { AuthUser, checkoutCounter, CounterSale, logout, lookupCounterBarcode } from './api'

type CartLine = { serial: string; name: string; price: number; available: number; quantity: number }
type Props = { user: AuthUser; onSignOut: () => void }

export default function CashierApp({ user, onSignOut }: Props) {
  const [code, setCode] = useState('')
  const [cart, setCart] = useState<CartLine[]>([])
  const [receipt, setReceipt] = useState<CounterSale | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const requestKey = useRef<string>(crypto.randomUUID())
  const inputRef = useRef<HTMLInputElement>(null)

  const total = cart.reduce((sum, line) => sum + line.price * line.quantity, 0)
  const units = cart.reduce((sum, line) => sum + line.quantity, 0)
  const notify = (text: string) => { setMessage(text); window.setTimeout(() => setMessage((current) => current === text ? '' : current), 3500) }

  async function addScan(raw: string) {
    const serial = raw.trim()
    if (!serial || busy) return
    setBusy(true)
    try {
      const item = await lookupCounterBarcode(serial)
      setReceipt(null)
      setCart((lines) => {
        const existing = lines.find((line) => line.serial === item.serial_number)
        if (!existing) return [...lines, { serial: item.serial_number, name: item.product_name, price: item.unit_price, available: item.available_quantity, quantity: 1 }]
        if (existing.quantity >= item.available_quantity) { notify(`Only ${item.available_quantity} of ${item.product_name} in stock`); return lines }
        return lines.map((line) => line.serial === item.serial_number ? { ...line, quantity: line.quantity + 1, available: item.available_quantity } : line)
      })
      setCode('')
    } catch (error) { notify(error instanceof Error ? error.message : 'Product not found') }
    finally { setBusy(false); inputRef.current?.focus() }
  }

  async function openCamera() {
    if (!Capacitor.isNativePlatform()) { notify('Use a handheld scanner or type the serial number'); return }
    try {
      const permission = await BarcodeScanner.requestPermissions()
      if (permission.camera !== 'granted') { notify('Camera permission is required'); return }
      const result = await BarcodeScanner.scan({ autoZoom: true })
      const value = result.barcodes[0]?.rawValue ?? ''
      if (value) await addScan(value)
    } catch { notify('Scanner unavailable; type the serial number') }
  }

  const change = (serial: string, delta: number) => setCart((lines) => lines.flatMap((line) => {
    if (line.serial !== serial) return [line]
    const quantity = line.quantity + delta
    if (quantity <= 0) return []
    if (quantity > line.available) { notify(`Only ${line.available} of ${line.name} in stock`); return [line] }
    return [{ ...line, quantity }]
  }))

  async function checkout() {
    if (!cart.length || busy) return
    setBusy(true)
    try {
      const sale = await checkoutCounter({ request_key: requestKey.current, items: cart.map((line) => ({ scanned_code: line.serial, quantity: line.quantity })) })
      setReceipt(sale); setCart([]); requestKey.current = crypto.randomUUID()
    } catch (error) { notify(error instanceof Error ? error.message : 'Checkout failed') }
    finally { setBusy(false); inputRef.current?.focus() }
  }

  function submit(event: FormEvent) { event.preventDefault(); void addScan(code) }

  return <div className="cashier-shell">
    <header className="cashier-top"><div className="brand"><div className="brand-mark"><PackageCheck size={19} /></div><div><strong>PantryOS Checkout</strong><span>{user.username}</span></div></div><button className="button subtle" onClick={() => { logout(); onSignOut() }}><LogOut size={16} /> Sign out</button></header>
    {message && <div className="toast"><ScanLine size={17} />{message}</div>}
    <main className="cashier-layout">
      <section className="panel scanner-card"><div className="scan-icon"><Barcode size={22} /></div><p className="eyebrow">Scanner</p><h2>Scan the product serial number</h2>
        <form onSubmit={submit}><div className="checkout-input"><Barcode size={18} /><input ref={inputRef} autoFocus={!window.matchMedia('(pointer: coarse)').matches} autoComplete="off" value={code} placeholder="Scan or type serial number" onChange={(event) => setCode(event.target.value)} /><button type="button" aria-label="Open camera scanner" title="Open camera scanner" onClick={() => void openCamera()}><Camera size={18} /></button></div></form>
        <button type="button" className="button primary scan-camera" onClick={() => void openCamera()}><Camera size={20} /> Scan with camera</button>
        <p className="field-hint">Scan the same item again to add one more. Use the buttons on the right to change or remove items.</p>
        {receipt && <div className="receipt-card"><ReceiptText size={20} /><strong>Sale complete · {receipt.bill_number}</strong><span>{receipt.items.reduce((sum, line) => sum + line.quantity, 0)} items · ${receipt.total_amount.toFixed(2)}</span></div>}
      </section>
      <section className="panel bill-card"><div className="table-toolbar"><div><p className="eyebrow">Current customer</p><h2>{units ? `${units} item${units === 1 ? '' : 's'}` : 'Nothing scanned yet'}</h2></div></div>
        {cart.length ? <div className="bill-lines">{cart.map((line) => <div className="bill-line cart-line" key={line.serial}><div><strong>{line.name}</strong><small>Serial {line.serial} · ${line.price.toFixed(2)} each</small></div><div className="qty-controls"><button aria-label={`Remove one ${line.name}`} onClick={() => change(line.serial, -1)}><Minus size={15} /></button><strong>{line.quantity}</strong><button aria-label={`Add one ${line.name}`} onClick={() => change(line.serial, 1)}><Plus size={15} /></button></div><strong>${(line.price * line.quantity).toFixed(2)}</strong><button className="icon-button" aria-label={`Remove ${line.name}`} title="Remove item" onClick={() => setCart((lines) => lines.filter((item) => item.serial !== line.serial))}><Trash2 size={16} /></button></div>)}</div> : <div className="empty-state"><Barcode size={28} /><strong>Ready for the next customer</strong><span>Scanned products appear here with their price.</span></div>}
        <div className="cart-bar"><div className="cart-total"><span>Total</span><strong>${total.toFixed(2)}</strong></div>
        <button className="button primary cart-checkout" disabled={!cart.length || busy} onClick={() => void checkout()}>Check out</button></div>
      </section>
    </main>
  </div>
}
