import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'

import { authApi } from '../../api/auth'
import type { Address, AddressInput } from '../../api/auth'
import { errorMessage } from '../../api/client'
import { Alert, EmptyState, Loading } from '../../components/ui'
import { AddressForm, EMPTY_ADDRESS } from './AddressForm'

/** null = closed, 'new' = adding, a number = editing that address. */
type Mode = null | 'new' | number

function toInput(address: Address): AddressInput {
  const { label, line1, line2, city, postal_code, is_default } = address
  return { label, line1, line2, city, postal_code, is_default }
}

export function AddressPanel() {
  const [addresses, setAddresses] = useState<Address[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>(null)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      setAddresses(await authApi.listAddresses())
    } catch (err) {
      setError(errorMessage(err, 'Could not load addresses.'))
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const save = (values: AddressInput) => {
    setBusy(true)
    setError(null)
    void (async () => {
      try {
        if (mode === 'new') await authApi.addAddress(values)
        else if (typeof mode === 'number') await authApi.updateAddress(mode, values)
        setMode(null)
        await load()
      } catch (err) {
        setError(errorMessage(err, 'Could not save address.'))
      } finally {
        setBusy(false)
      }
    })()
  }

  const remove = (id: number) => {
    void (async () => {
      try {
        await authApi.deleteAddress(id)
        if (mode === id) setMode(null)
        await load()
      } catch (err) {
        setError(errorMessage(err, 'Could not delete address.'))
      }
    })()
  }

  const editing = typeof mode === 'number' ? addresses?.find((a) => a.id === mode) : undefined

  return (
    <section className="card panel">
      <h3>
        Delivery addresses
        <button className="link-btn" onClick={() => setMode((m) => (m === 'new' ? null : 'new'))}>
          {mode === 'new' ? 'Cancel' : '+ Add'}
        </button>
      </h3>

      {error && <Alert>{error}</Alert>}

      {mode !== null && (
        <AddressForm
          // Remount on mode change so the prefill follows the selected address.
          key={String(mode)}
          initial={editing ? toInput(editing) : EMPTY_ADDRESS}
          submitLabel={editing ? 'Save changes' : 'Save address'}
          busy={busy}
          onSubmit={save}
          onCancel={() => setMode(null)}
        />
      )}

      {addresses === null ? (
        <Loading />
      ) : addresses.length === 0 ? (
        <EmptyState>No addresses yet. Add one to speed up checkout.</EmptyState>
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
              <div className="addr-actions">
                <button
                  className="icon-btn"
                  title={`Edit ${a.label}`}
                  aria-label={`Edit ${a.label}`}
                  onClick={() => setMode(a.id)}
                >
                  ✎
                </button>
                <button
                  className="icon-btn"
                  title={`Delete ${a.label}`}
                  aria-label={`Delete ${a.label}`}
                  onClick={() => remove(a.id)}
                >
                  ✕
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </section>
  )
}
