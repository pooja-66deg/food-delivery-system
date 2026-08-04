import { useState } from 'react'
import type { FormEvent } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi } from '../../api/restaurants'
import type { Restaurant } from '../../api/restaurants'
import { Alert, Button, Field, PhoneField } from '../../components/ui'
import { normalizePhone, PHONE_ERROR } from '../../lib/phone'

const EMPTY = {
  name: '',
  city: '',
  address_line: '',
  phone: '',
  min_order_amount: '0',
  delivery_radius_km: '',
}

export function RestaurantForm({ onCreated }: { onCreated: (r: Restaurant) => void }) {
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function set(field: keyof typeof form) {
    return (e: { target: { value: string } }) => setForm((f) => ({ ...f, [field]: e.target.value }))
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    const phone = normalizePhone(form.phone)
    if (phone === null) {
      setError(PHONE_ERROR)
      return
    }
    setError(null)
    setBusy(true)
    try {
      const r = await restaurantsApi.create({
        name: form.name,
        city: form.city,
        address_line: form.address_line,
        phone,
        min_order_amount: Number(form.min_order_amount) || 0,
        // Left blank means "use the platform default", which the API expresses
        // as an absent field rather than a zero.
        delivery_radius_km: form.delivery_radius_km
          ? Number(form.delivery_radius_km)
          : undefined,
      })
      setForm(EMPTY)
      onCreated(r)
    } catch (err) {
      setError(errorMessage(err, 'Could not create restaurant.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="owner-form" onSubmit={submit}>
      <h3>New restaurant</h3>
      {error && <Alert>{error}</Alert>}
      <Field label="Name" value={form.name} onChange={set('name')} required />
      <Field label="City" value={form.city} onChange={set('city')} required />
      <Field label="Address" value={form.address_line} onChange={set('address_line')} required />
      <PhoneField
        label="Phone"
        name="phone"
        value={form.phone}
        onChange={(phone) => setForm((f) => ({ ...f, phone }))}
        required
      />
      <Field
        label="Minimum order amount"
        type="number"
        min="0"
        step="0.01"
        value={form.min_order_amount}
        onChange={set('min_order_amount')}
      />
      <Field
        label="Delivery radius (km)"
        name="delivery_radius_km"
        type="number"
        min="0.5"
        max="100"
        step="0.5"
        placeholder="Leave blank for the default"
        value={form.delivery_radius_km}
        onChange={set('delivery_radius_km')}
      />
      <Button block loading={busy}>Create restaurant</Button>
    </form>
  )
}
