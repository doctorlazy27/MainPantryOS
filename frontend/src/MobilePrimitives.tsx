import { useEffect, useState } from 'react'
import { Network } from '@capacitor/network'
import { StatusBar, Style } from '@capacitor/status-bar'
import { WifiOff } from 'lucide-react'
import { pingServer } from './api'

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
  useEffect(() => {
    void StatusBar.setOverlaysWebView({ overlay: false }).catch(() => undefined)
    void StatusBar.setStyle({ style: Style.Light }).catch(() => undefined)
    let listener: { remove: () => Promise<void> } | undefined
    let timer = 0
    // The plugin can report "disconnected" on emulators, VPNs or captive networks, so the server itself is the source of truth.
    const verify = async (pluginConnected: boolean) => {
      window.clearTimeout(timer)
      if (pluginConnected) { setOnline(true); return }
      const reachable = await pingServer()
      setOnline(reachable)
      if (!reachable) timer = window.setTimeout(() => void Network.getStatus().then((status) => verify(status.connected)).catch(() => verify(false)), 15000)
    }
    void Network.getStatus().then((status) => verify(status.connected)).catch(() => undefined)
    void Network.addListener('networkStatusChange', (status) => void verify(status.connected)).then((handle) => { listener = handle })
    return () => { window.clearTimeout(timer); void listener?.remove() }
  }, [])
  if (online) return null
  return <div className="connection-pill offline" role="status" aria-live="polite"><WifiOff size={14} /><span>Can't reach the server</span></div>
}
