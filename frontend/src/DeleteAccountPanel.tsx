import { FormEvent, useState } from 'react'
import { deleteOwnAccount } from './api'

type Props = { onToast: (message: string) => void; onDeleted: () => void }

export default function DeleteAccountPanel({ onToast, onDeleted }: Props) {
  const [password, setPassword] = useState('')
  const [confirming, setConfirming] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    try { await deleteOwnAccount(password); onToast('Account deleted'); onDeleted() }
    catch (error) { onToast(error instanceof Error ? error.message : 'Could not delete the account') }
  }

  return <section className="panel workflow-card"><p className="eyebrow">My account</p><h2>Delete my account</h2><p>Deleting your account is permanent. You can sign up again afterwards, including with a different warehouse. Your past work stays on record under your manager.</p>{confirming ? <form className="form-grid" onSubmit={(event) => void submit(event)}><label>Confirm your password<input required autoFocus type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label><div className="form-actions"><button className="button subtle" type="button" onClick={() => { setConfirming(false); setPassword('') }}>Cancel</button><button className="button primary" type="submit">Delete account</button></div></form> : <button className="button primary" onClick={() => setConfirming(true)}>Delete my account</button>}</section>
}
