import { FormEvent, useEffect, useState } from 'react'
import { IncomingMessage, getMessageContacts, getMessages, markMessageRead, MessageContact, sendMessage, Role } from './api'

type Props = { role: Role }

export default function MessagingPanel({ role }: Props) {
  const [contacts, setContacts] = useState<MessageContact[]>([])
  const [messages, setMessages] = useState<IncomingMessage[]>([])
  const [selected, setSelected] = useState<number[]>([])
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [broadcast, setBroadcast] = useState(false)
  const [replyingTo, setReplyingTo] = useState<number | null>(null)
  const [replyBody, setReplyBody] = useState('')
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [refreshing, setRefreshing] = useState(false)

  async function load(showStatus = false) {
    if (showStatus) setRefreshing(true)
    try {
      const [contactData, messageData] = await Promise.all([getMessageContacts(), getMessages()])
      setContacts(contactData.contacts)
      setMessages(messageData.messages)
      setError('')
      if (showStatus) setStatus(`Inbox updated at ${new Date().toLocaleTimeString()}`)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load messages')
      if (showStatus) setStatus('Refresh failed')
    } finally {
      if (showStatus) setRefreshing(false)
    }
  }

  useEffect(() => {
    void load()
    const interval = window.setInterval(() => void load(), 5000)
    return () => window.clearInterval(interval)
  }, [])

  function selectedContacts(event: React.ChangeEvent<HTMLSelectElement>) {
    setSelected(Array.from(event.target.selectedOptions, (option) => Number(option.value)))
  }

  function toggleRecipient(userId: number) {
    setSelected((current) => current.includes(userId) ? current.filter((id) => id !== userId) : [...current, userId])
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setStatus('')
    try {
      await sendMessage({ recipient_ids: selected, subject, body, broadcast })
      setSubject('')
      setBody('')
      setSelected([])
      setBroadcast(false)
      setStatus('Message sent')
      await load()
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : 'Could not send message')
    }
  }

  async function reply(message: IncomingMessage) {
    try {
      await sendMessage({ recipient_ids: [message.sender_id], subject: `Re: ${message.subject}`, body: replyBody, reply_to_id: message.message_id })
      setReplyBody('')
      setReplyingTo(null)
      setStatus('Reply sent')
      await load()
    } catch (replyError) {
      setError(replyError instanceof Error ? replyError.message : 'Could not send reply')
    }
  }

  async function read(message: IncomingMessage) {
    if (message.is_read) return
    await markMessageRead(message.message_id)
    await load()
  }

  return <>
    <section className="panel workflow-card">
      <p className="eyebrow">Internal messaging</p>
      <h2>Send a message</h2>
      <form className="stack-form" onSubmit={submit}>
        {!broadcast && <fieldset className="recipient-field"><legend>Recipients</legend>{contacts.length ? <div className="recipient-list">{contacts.map((contact) => <label className={`recipient-option ${selected.includes(contact.user_id) ? 'selected' : ''}`} key={contact.user_id}><input type={role === 'manager' ? 'checkbox' : 'radio'} name="message-recipient" checked={selected.includes(contact.user_id)} onChange={() => role === 'manager' ? toggleRecipient(contact.user_id) : setSelected([contact.user_id])} /><span><strong>{contact.full_name}</strong><small>{contact.role.replace('_', ' ')}</small></span></label>)}</div> : <p className="field-hint">No eligible contacts in your warehouse.</p>}</fieldset>}
        {role === 'manager' && <label className="checkbox-field"><input type="checkbox" checked={broadcast} onChange={(event) => setBroadcast(event.target.checked)} /> Send to all warehouse users</label>}
        <label>Subject<input required maxLength={150} value={subject} onChange={(event) => setSubject(event.target.value)} /></label>
        <label>Message<textarea required maxLength={5000} rows={4} value={body} onChange={(event) => setBody(event.target.value)} /></label>
        {error && <div className="auth-error">{error}</div>}
        {status && <div className="auth-success">{status}</div>}
        <button className="button primary" type="submit">Send message</button>
      </form>
    </section>
    <section className="panel data-panel">
      <div className="table-toolbar"><div><p className="eyebrow">Inbox</p><h2>{messages.length} messages</h2></div><button className="button subtle" disabled={refreshing} onClick={() => void load(true)}>{refreshing ? 'Refreshing...' : 'Refresh inbox'}</button></div>
      {messages.length ? <div className="notification-list">{messages.map((message) => <article className={`notification ${message.is_read ? '' : 'unread'}`} key={message.message_id} onClick={() => void read(message)}><div><strong>{message.subject}</strong><p>{message.body}</p><span>From {message.sender_username} · {new Date(message.created_at).toLocaleString()}</span></div>{!message.is_read && <button className="row-action" onClick={(event) => { event.stopPropagation(); void read(message) }}>Mark read</button>}{message.can_reply && <>{replyingTo === message.message_id ? <form className="stack-form" onSubmit={(event) => { event.preventDefault(); void reply(message) }} onClick={(event) => event.stopPropagation()}><textarea required rows={3} value={replyBody} onChange={(event) => setReplyBody(event.target.value)} placeholder="Write a reply" /><button className="row-action" type="submit">Send reply</button></form> : <button className="row-action" onClick={(event) => { event.stopPropagation(); setReplyingTo(message.message_id) }}>Reply</button>}</>}</article>)}</div> : <p>No messages yet.</p>}
    </section>
  </>
}
