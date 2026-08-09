import { useState } from 'react'
import type { FormEvent } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi, FOOD_TYPE_LABELS } from '../../api/restaurants'
import type { FoodType, Restaurant } from '../../api/restaurants'
import { Alert, Button, Field, PhoneField } from '../../components/ui'
import { normalizePhone, PHONE_ERROR } from '../../lib/phone'
import { AddressAutocomplete } from '../../components/AddressAutocomplete'
import { CityDropdown } from '../../components/CityDropdown'

const EMPTY = {
  name: '',
  city: '',
  address_line: '',
  phone: '',
  min_order_amount: '0',
  delivery_radius_km: '',
  // "Both" is the honest starting point for a kitchen nobody has asked yet.
  // Defaulting to veg would assert a claim the owner never made, and the
  // customer Vegetarian filter reads this field.
  food_type: 'both' as FoodType,
}

const FOOD_TYPES = Object.keys(FOOD_TYPE_LABELS) as FoodType[]

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
        food_type: form.food_type,
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
    // No heading of its own: the dialog that hosts this form already has one.
    <form className="owner-form" onSubmit={submit}>
      {error && <Alert>{error}</Alert>}
      <Field label="Name" name="name" value={form.name} onChange={set('name')} required />
      <CityDropdown
        value={form.city}
        onChange={(city) => setForm({ ...form, city })}
        required
      />
      <AddressAutocomplete
        value={form.address_line}
        onChange={(address_line) => setForm({ ...form, address_line })}
      />
      <PhoneField
        label="Phone"
        name="phone"
        value={form.phone}
        onChange={(phone) => setForm((f) => ({ ...f, phone }))}
        required
      />
      {/* htmlFor/id rather than a wrapping label, matching Field: the helper
          text below would otherwise be folded into the control's accessible
          name, which is what a screen reader announces on focus. */}
      <div className="field">
        <label htmlFor="food_type">Food type</label>
        <select
          id="food_type"
          className="input"
          name="food_type"
          value={form.food_type}
          onChange={(e) => setForm((f) => ({ ...f, food_type: e.target.value as FoodType }))}
        >
          {FOOD_TYPES.map((t) => (
            <option key={t} value={t}>
              {FOOD_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
        <small className="muted">
          What your kitchen serves. Customers filtering for vegetarian see only
          restaurants set to “Vegetarian”.
        </small>
      </div>
      <Field
        label="Minimum order amount"
        name="min_order_amount"
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
      <Button block loading={busy}>Register restaurant</Button>
      <small className="muted">
        An administrator reviews new restaurants. You can build your menu straight away;
        customers see it once it is approved.
      </small>
    </form>
  )
}
