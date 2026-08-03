import { useState } from 'react'
import type { FormEvent } from 'react'

import { authApi } from '../../api/auth'
import { errorMessage } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import { Alert, Button, PasswordField } from '../../components/ui'

const EMPTY = { current: '', next: '', confirm: '' }

export function SecurityPanel() {
  const { replaceTokens } = useAuth()
  const [form, setForm] = useState(EMPTY)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (form.next !== form.confirm) {
      setMsg({ kind: 'error', text: 'The new passwords do not match.' })
      return
    }
    setBusy(true)
    setMsg(null)
    void (async () => {
      try {
        // The change invalidates every existing token, including the one this
        // tab is holding — store the replacement pair the server returns.
        replaceTokens(await authApi.changePassword(form.current, form.next))
        setForm(EMPTY)
        setMsg({ kind: 'ok', text: 'Password changed. Other devices have been signed out.' })
      } catch (err) {
        setMsg({ kind: 'error', text: errorMessage(err, 'Could not change password.') })
      } finally {
        setBusy(false)
      }
    })()
  }

  return (
    <section className="card panel">
      <h3>Password</h3>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <form className="form-stack" onSubmit={submit} style={{ marginTop: msg ? '1rem' : 0 }}>
        <PasswordField
          label="Current password"
          name="current_password"
          autoComplete="current-password"
          value={form.current}
          onChange={set('current')}
          required
        />
        <PasswordField
          label="New password"
          name="new_password"
          autoComplete="new-password"
          minLength={8}
          title="At least 8 characters"
          value={form.next}
          onChange={set('next')}
          required
        />
        <PasswordField
          label="Confirm new password"
          name="confirm_password"
          autoComplete="new-password"
          minLength={8}
          value={form.confirm}
          onChange={set('confirm')}
          required
        />
        <Button type="submit" loading={busy}>
          Change password
        </Button>
      </form>
    </section>
  )
}
