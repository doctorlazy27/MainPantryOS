import { useState } from 'react'
import { Role } from './api'
import InventoryOverview from './InventoryOverview'
import InventoryRequestsPanel from './InventoryRequestsPanel'

type Props = { role: Role; onToast: (message: string) => void }

export default function InventoryHub({ role, onToast }: Props) {
  const [tab, setTab] = useState<'products' | 'requests'>('products')
  return <>
    <div className="segmented" role="tablist"><button role="tab" aria-selected={tab === 'products'} className={tab === 'products' ? 'active' : ''} onClick={() => setTab('products')}>Products</button><button role="tab" aria-selected={tab === 'requests'} className={tab === 'requests' ? 'active' : ''} onClick={() => setTab('requests')}>Stock requests</button></div>
    {tab === 'products' ? <InventoryOverview role={role} onToast={onToast} /> : <InventoryRequestsPanel role={role} onToast={onToast} />}
  </>
}
