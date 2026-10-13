import { FormEvent, useEffect, useState } from 'react'
import { AlertTriangle, ArrowRight, CheckCircle2, Mail, PackageCheck, RotateCcw } from 'lucide-react'
import { getSignupWarehouses, login, register, requestPasswordReset, requestSignupOtp, resetPassword, Role, Warehouse } from './api'
import AppSelect from './AppSelect'
import WarehouseSignupControl from './WarehouseSignupControl'

type Props = { onLogin: (user: Awaited<ReturnType<typeof login>>) => void }
type Mode = 'login' | 'signup' | 'reset'

export default function AuthAccess({ onLogin }: Props) {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [otp, setOtp] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<Role>('manager')
  const [warehouseInput, setWarehouseInput] = useState('')
  const [creatingWarehouse, setCreatingWarehouse] = useState(false)
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const isLogin = mode === 'login'
  const isSignup = mode === 'signup'

  useEffect(() => {
    if (isSignup) void getSignupWarehouses().then((data) => {
      setWarehouses(data.warehouses)
      if (!data.warehouses.length && role === 'manager') setCreatingWarehouse(true)
    }).catch(() => setError('Could not load warehouses'))
  }, [isSignup])

  function switchMode(nextMode: Mode) {
    setMode(nextMode)
    setError('')
    setMessage('')
    setOtp('')
    setPassword('')
  }

  async function sendCode() {
    setLoading(true)
    setError('')
    try {
      const result = isSignup ? await requestSignupOtp(email) : await requestPasswordReset(email)
      setMessage(result.dev_otp ? `Verification code sent. Development code: ${result.dev_otp}` : result.message)
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Could not send verification code')
    } finally {
      setLoading(false)
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    setMessage('')
    try {
      if (isLogin) {
        onLogin(await login(email, password))
      } else if (mode === 'reset') {
        const result = await resetPassword({ email, otp, new_password: password })
        setMode('login')
        setMessage(result.message)
      } else {
        const numericWarehouseId = Number(warehouseInput)
        const result = await register({ full_name: fullName, email, otp, password, role, warehouse_id: !creatingWarehouse && numericWarehouseId > 0 ? numericWarehouseId : undefined, warehouse_name: creatingWarehouse ? warehouseInput.trim() : undefined })
        setMessage(result.message)
        setPassword('')
        setOtp('')
      }
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  return <div className="auth-shell"><div className="auth-visual"><div className="auth-brand"><div className="brand-mark"><PackageCheck size={19} /></div><strong>PantryOS</strong></div><div className="auth-visual-copy"><p className="eyebrow">Warehouse inventory control</p><h1>Every unit accounted for.</h1><p>Receive, scan, replenish, and audit stock from one warehouse workspace.</p></div></div><div className="auth-form-wrap"><form className="auth-form" onSubmit={submit}><div className="auth-tabs"><button type="button" className={isLogin ? 'active' : ''} onClick={() => switchMode('login')}>Sign in</button><button type="button" className={isSignup ? 'active' : ''} onClick={() => switchMode('signup')}>Create account</button></div><p className="eyebrow">{isLogin ? 'Secure access' : mode === 'reset' ? 'Account recovery' : 'Email verification'}</p><h2>{isLogin ? 'Sign in to PantryOS' : mode === 'reset' ? 'Reset your password' : 'Create a warehouse account'}</h2><p className="auth-intro">{isLogin ? 'Use your account email and password.' : mode === 'reset' ? 'We will verify your email before changing the password.' : 'Verify your email before your account request is created.'}</p>{isSignup && <><label>Full name<input required value={fullName} onChange={(event) => setFullName(event.target.value)} /></label><WarehouseSignupControl role={role} warehouses={warehouses} creatingWarehouse={creatingWarehouse} warehouseInput={warehouseInput} onCreatingWarehouseChange={setCreatingWarehouse} onWarehouseInputChange={setWarehouseInput} /><label>Requested role<AppSelect value={role} onChange={(event) => { const nextRole = event.target.value as Role; setRole(nextRole); if (nextRole === 'warehouse_worker') { setCreatingWarehouse(false); setWarehouseInput('') } }}><option value="warehouse_worker">Warehouse worker</option><option value="manager">Manager</option></AppSelect></label></>}{!isLogin && <label>Email address<div className="input-action"><Mail size={16} /><input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} /><button type="button" onClick={() => void sendCode()} aria-label="Send verification code" title="Send verification code"><RotateCcw size={16} /></button></div></label>}{isLogin && <label>Email address<div className="input-action"><Mail size={16} /><input autoFocus required type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></div></label>}{!isLogin && <label>Verification code<input required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, ''))} /></label>}<label>{isLogin || isSignup ? 'Password' : 'New password'}<input required minLength={8} type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>{error && <div className="auth-error"><AlertTriangle size={15} />{error}</div>}{message && <div className="auth-success"><CheckCircle2 size={15} />{message}</div>}<button className="button primary" type="submit" disabled={loading}>{loading ? 'Working...' : isLogin ? 'Continue' : isSignup ? 'Create account' : 'Update password'} <ArrowRight size={16} /></button>{isLogin && <button type="button" className="link-button auth-forgot" onClick={() => switchMode('reset')}>Forgot password?</button>}{mode === 'reset' && <button type="button" className="link-button auth-forgot" onClick={() => switchMode('login')}>Back to sign in</button>}</form></div></div>
}
