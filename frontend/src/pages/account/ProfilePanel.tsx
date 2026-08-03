import { useState } from 'react'
import type { FormEvent } from 'react'

import { authApi } from '../../api/auth'
import { errorMessage } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import { Alert, Button, Field, PhoneField } from '../../components/ui'
import { filterNameInput } from '../../lib/inputFilters'
import { normalizePhone, PHONE_ERROR } from '../../lib/phone'

export function ProfilePanel() {
  const { user, setUser } = useAuth()
  const [form, setForm] = useState({
    first_name: user?.first_name ?? '',
    last_name: user?.last_name ?? '',
    phone: user?.phone ?? '',
  })
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)

  // Same keystroke filters as the register form, so invalid characters never
  // reach the API and come back as a 422.
  const setFiltered =
    (key: keyof typeof form, filter: (v: string) => string) =>
    (e: { target: { value: string } }) =>
      setForm((f) => ({ ...f, [key]: filter(e.target.value) }))

  const save = (e: FormEvent) => {
    e.preventDefault()
    const phone = normalizePhone(form.phone)
    if (phone === null) {
      setMsg({ kind: 'error', text: PHONE_ERROR })
      return
    }
    setBusy(true)
    setMsg(null)
    void (async () => {
      try {
        const updated = await authApi.updateProfile({ ...form, phone })
        setUser(updated)
        setMsg({ kind: 'ok', text: 'Profile updated.' })
      } catch (err) {
        setMsg({ kind: 'error', text: errorMessage(err, 'Update failed.') })
      } finally {
        setBusy(false)
      }
    })()
  }

  if (!user) return null

  return (
    <section className="card panel">
      <h3>Profile</h3>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <form className="form-stack" onSubmit={save} style={{ marginTop: msg ? '1rem' : 0 }}>
        <div className="form-row">
          <Field
            label="First name"
            name="first_name"
            value={form.first_name}
            onChange={setFiltered('first_name', filterNameInput)}
            pattern="[A-Za-z ]+"
            title="Letters only"
            required
          />
          <Field
            label="Last name"
            name="last_name"
            value={form.last_name}
            onChange={setFiltered('last_name', filterNameInput)}
            pattern="[A-Za-z ]+"
            title="Letters only"
            required
          />
        </div>
        <PhoneField
          label="Phone"
          name="phone"
          value={form.phone}
          onChange={(phone) => setForm((f) => ({ ...f, phone }))}
          required
        />
        <div className="field">
          <label>Email</label>
          <input className="input" value={user.email} disabled />
        </div>
        <Button type="submit" loading={busy}>
          Save changes
        </Button>
      </form>
    </section>
  )
}
