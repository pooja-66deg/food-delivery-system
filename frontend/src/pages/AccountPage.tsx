import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { motion } from 'framer-motion'

import { authApi } from '../api/auth'
import type { Address, AddressInput } from '../api/auth'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Alert, Button, Field } from '../components/ui'

const EMPTY_ADDRESS: AddressInput = {
  label: 'home',
  line1: '',
  line2: '',
  city: '',
  postal_code: '',
  is_default: false,
}

export function AccountPage() {
  const { user } = useAuth()

  return (
    <main className="app-main">
      <motion.div
        className="page-head"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
      >
        <span className="chip chip-accent">Your account</span>
        <h1 style={{ marginTop: '0.6rem' }}>
          Hello, {user?.first_name} {user?.last_name}
        </h1>
        <p>Manage your profile details and delivery addresses.</p>
      </motion.div>

      <div className="account-grid">
        <ProfilePanel />
        <AddressPanel />
      </div>
    </main>
  )
}

function ProfilePanel() {
  const { user, setUser } = useAuth()
  const [form, setForm] = useState({
    first_name: user?.first_name ?? '',
    last_name: user?.last_name ?? '',
    phone: user?.phone ?? '',
  })
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const save = (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setMsg(null)
    void (async () => {
      try {
        const updated = await authApi.updateProfile(form)
        setUser(updated)
        setMsg({ kind: 'ok', text: 'Profile updated.' })
      } catch (err) {
        setMsg({ kind: 'error', text: err instanceof ApiError ? err.message : 'Update failed.' })
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
          <Field label="First name" name="first_name" value={form.first_name} onChange={set('first_name')} required />
          <Field label="Last name" name="last_name" value={form.last_name} onChange={set('last_name')} required />
        </div>
        <Field label="Phone" name="phone" type="tel" value={form.phone} onChange={set('phone')} required />
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

function AddressPanel() {
  const [addresses, setAddresses] = useState<Address[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<AddressInput>(EMPTY_ADDRESS)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      setAddresses(await authApi.listAddresses())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load addresses.')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const set = (key: keyof AddressInput) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const add = (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    void (async () => {
      try {
        await authApi.addAddress(form)
        setForm(EMPTY_ADDRESS)
        setShowForm(false)
        await load()
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Could not save address.')
      } finally {
        setBusy(false)
      }
    })()
  }

  const remove = (id: number) => {
    void (async () => {
      try {
        await authApi.deleteAddress(id)
        await load()
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Could not delete address.')
      }
    })()
  }

  return (
    <section className="card panel">
      <h3>
        Delivery addresses
        <button className="link-btn" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Add'}
        </button>
      </h3>

      {error && <Alert>{error}</Alert>}

      {showForm && (
        <form className="form-stack" onSubmit={add} style={{ marginBottom: '1.25rem', marginTop: error ? '1rem' : 0 }}>
          <Field label="Label" name="label" placeholder="home, work…" value={form.label} onChange={set('label')} required />
          <Field label="Address line 1" name="line1" placeholder="221B Baker Street" value={form.line1} onChange={set('line1')} required />
          <Field label="Address line 2" name="line2" placeholder="Apt, suite (optional)" value={form.line2 ?? ''} onChange={set('line2')} />
          <div className="form-row">
            <Field label="City" name="city" value={form.city} onChange={set('city')} required />
            <Field label="Postal code" name="postal_code" value={form.postal_code} onChange={set('postal_code')} required />
          </div>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => setForm((f) => ({ ...f, is_default: e.target.checked }))}
            />
            Set as default address
          </label>
          <Button type="submit" loading={busy}>
            Save address
          </Button>
        </form>
      )}

      {addresses === null ? (
        <div className="empty">
          <span className="spin" aria-hidden /> Loading…
        </div>
      ) : addresses.length === 0 ? (
        <div className="empty">No addresses yet. Add one to speed up checkout.</div>
      ) : (
        <div className="address-list">
          {addresses.map((a) => (
            <motion.div
              key={a.id}
              className="address-card"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div>
                <div className="addr-label">
                  {a.label}
                  {a.is_default && <span className="chip chip-accent">Default</span>}
                </div>
                <div className="addr-lines">
                  {a.line1}
                  {a.line2 ? `, ${a.line2}` : ''}
                  <br />
                  {a.city} {a.postal_code}
                </div>
              </div>
              <button className="icon-btn" title="Delete address" onClick={() => remove(a.id)}>
                ✕
              </button>
            </motion.div>
          ))}
        </div>
      )}
    </section>
  )
}
