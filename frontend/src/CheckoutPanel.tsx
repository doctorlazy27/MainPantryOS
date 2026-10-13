import { FormEvent, useState } from 'react'
import { Barcode, Camera, ScanLine } from 'lucide-react'
import { Capacitor } from '@capacitor/core'
import { Haptics, NotificationType } from '@capacitor/haptics'
import { BarcodeScanner } from '@capacitor-mlkit/barcode-scanning'
import { checkoutCounter } from './api'

type ScanResult = { id: string; code: string; name: string; remaining: number; bill: string }
type Props = { onToast: (message: string) => void }

export default function CheckoutPanel({ onToast }: Props) {
  const [code, setCode] = useState('')
  const [scans, setScans] = useState<ScanResult[]>([])
  const [processing, setProcessing] = useState(false)
  const [pendingScan, setPendingScan] = useState<{ code: string; requestKey: string } | null>(null)

  async function processCode(rawCode: string) {
    const value = rawCode.trim()
    if (!value || processing) return
    setProcessing(true)
    try {
      const requestKey = pendingScan?.code === value ? pendingScan.requestKey : crypto.randomUUID()
      setPendingScan({ code: value, requestKey })
      const result = await checkoutCounter({ request_key: requestKey, items: [{ scanned_code: value, quantity: 1 }] })
      if (result.duplicate) {
        setCode('')
        setPendingScan(null)
        onToast(`Sale ${result.bill_number} was already recorded`)
        return
      }
      const remaining = result.remaining_quantity
      setScans((items) => [{ id: `${result.sale_id}-${value}`, code: value, name: result.product_name, remaining, bill: result.bill_number }, ...items].slice(0, 30))
      setCode('')
      setPendingScan(null)
      onToast(`${result.product_name} sold. ${remaining} units remain.`)
    } catch (error) {
      setCode(value)
      onToast(error instanceof Error ? error.message : 'Could not reduce counter stock')
    } finally {
      setProcessing(false)
    }
  }

  async function scan() {
    if (!Capacitor.isNativePlatform()) { onToast('Use the barcode field in the browser or scan on mobile'); return }
    try {
      const permission = await BarcodeScanner.requestPermissions()
      if (permission.camera !== 'granted') { onToast('Camera permission is required'); return }
      const result = await BarcodeScanner.scan({ autoZoom: true })
      const value = result.barcodes[0]?.rawValue ?? ''
      if (value) {
        await processCode(value)
        void Haptics.notification({ type: NotificationType.Success }).catch(() => undefined)
      }
    } catch { onToast('Scanner unavailable; enter the barcode manually') }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    await processCode(code)
  }

  return <>
    <section className="checkout-hero"><div><p className="eyebrow">Counter scanner</p><h1>Scan and sell</h1><p>Every successful scan sells one unit immediately and reduces counter stock.</p></div><div className="checkout-badge"><ScanLine size={20} /><span>{processing ? 'Processing' : 'Ready to scan'}</span></div></section>
    <section className="checkout-layout"><section className="panel scanner-card"><div className="scan-icon"><Barcode size={22} /></div><p className="eyebrow">Barcode scanner</p><h2>What was scanned</h2><form onSubmit={(event) => void submit(event)}><div className="checkout-input"><Barcode size={18} /><input autoFocus inputMode="text" value={code} placeholder="Scan barcode here" onChange={(event) => setCode(event.target.value)} /><button type="button" aria-label="Open camera scanner" title="Open camera scanner" onClick={() => void scan()}><Camera size={18} /></button></div></form><p className="field-hint">Scan continuously. Unknown, expired, or empty counter stock is rejected by the server.</p></section><section className="panel bill-card"><div className="table-toolbar"><div><p className="eyebrow">Scan history</p><h2>{scans.length ? `${scans.length} scanned` : 'Nothing scanned yet'}</h2></div></div>{scans.length ? <div className="bill-lines">{scans.map((item) => <div className="bill-line" key={item.id}><div><strong>{item.name}</strong><small>{item.code} · {item.bill}</small></div><span>{item.remaining} left</span></div>)}</div> : <div className="empty-state"><Barcode size={28} /><strong>Ready for the next scan</strong><span>The scanned product will appear here after its unit is deducted.</span></div>}</section></section>
  </>
}