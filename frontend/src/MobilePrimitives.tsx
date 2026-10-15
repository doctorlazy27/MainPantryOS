import { useEffect, useState } from 'react'
import { Network } from '@capacitor/network'
import { StatusBar, Style } from '@capacitor/status-bar'
import { Wifi, WifiOff } from 'lucide-react'

// Copies each table header label onto its row cells so stacked mobile cards stay readable.
export function TableLabels() {
  useEffect(() => {
    let frame = 0
    const apply = () => {
      document.querySelectorAll('.data-table').forEach((table) => {
        const head = table.querySelector(':scope > .data-head')
        if (!head) return
        const labels = Array.from(head.children).map((cell) => cell.textContent?.trim() ?? '')
        table.querySelectorAll(':scope > .data-row').forEach((row) => {
          row.setAttribute('data-labelled', '')
          Array.from(row.children).forEach((cell, index) => { if (index > 0 && labels[index] && cell.getAttribute('data-label') !== labels[index]) cell.setAttribute('data-label', labels[index]) })
        })
      })
    }
    const observer = new MutationObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(apply) })
    observer.observe(document.body, { childList: true, subtree: true })
    apply()
    return () => { observer.disconnect(); cancelAnimationFrame(frame) }
  }, [])
  return null
}

export function NativeAppEffects() {
  const [online, setOnline] = useState(true)
  const [showState, setShowState] = useState(false)
  useEffect(() => {
    void StatusBar.setOverlaysWebView({ overlay: false }).catch(() => undefined)
    void StatusBar.setStyle({ style: Style.Light }).catch(() => undefined)
    let listener: { remove: () => Promise<void> } | undefined
    void Network.getStatus().then((status) => setOnline(status.connected)).catch(() => undefined)
    void Network.addListener('networkStatusChange', (status) => { setOnline(status.connected); setShowState(true); window.setTimeout(() => setShowState(false), 2400) }).then((handle) => { listener = handle })
    return () => { void listener?.remove() }
  }, [])
  if (online) return null
  return <div className={`connection-pill ${showState ? 'visible' : ''} ${online ? 'connected' : 'offline'}`} aria-live="polite">{online ? <Wifi size={14} /> : <WifiOff size={14} />}<span>{online ? 'Connected' : 'Offline'}</span></div>
}
