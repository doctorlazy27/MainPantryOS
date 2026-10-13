import AppSelect from './AppSelect'
import { Role, Warehouse } from './api'

type Props = {
  role: Role
  warehouses: Warehouse[]
  creatingWarehouse: boolean
  warehouseInput: string
  onCreatingWarehouseChange: (creating: boolean) => void
  onWarehouseInputChange: (value: string) => void
}

export default function WarehouseSignupControl({ role, warehouses, creatingWarehouse, warehouseInput, onCreatingWarehouseChange, onWarehouseInputChange }: Props) {
  return <>
    {role === 'manager' && <label className="checkbox-field"><input type="checkbox" checked={creatingWarehouse} onChange={(event) => { onCreatingWarehouseChange(event.target.checked); onWarehouseInputChange('') }} /> Create a new warehouse</label>}
    {role === 'manager' && creatingWarehouse
      ? <label>New warehouse name<input required value={warehouseInput} placeholder="Enter warehouse name" onChange={(event) => onWarehouseInputChange(event.target.value)} /></label>
      : <>
          <label>Existing warehouse<AppSelect required value={warehouseInput} onChange={(event) => onWarehouseInputChange(event.target.value)}><option value="">Select warehouse</option>{warehouses.map((warehouse) => <option key={warehouse.warehouse_id} value={String(warehouse.warehouse_id)}>{warehouse.name}</option>)}</AppSelect></label>
          {role === 'warehouse_worker' && !warehouses.length && <p className="field-hint">A manager must create a warehouse before worker accounts can be requested.</p>}
        </>}
  </>
}