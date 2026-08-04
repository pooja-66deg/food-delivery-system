import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi } from '../../api/restaurants'
import { Alert, Button, Field } from '../../components/ui'

interface DeliveryZonePanelProps {
  restaurantId: number
  /** The owner's current setting, or null when the default applies. */
  radiusKm: number | null
  onSaved: () => void
}

/**
 * Edit how far a restaurant delivers.
 *
 * Separate from the create form because the radius is the one delivery setting
 * an owner revisits — trade grows, a new driver covers more ground — and it was
 * otherwise set once at creation and never editable.
 */
export function DeliveryZonePanel({ restaurantId, radiusKm, onSaved }: DeliveryZonePanelProps) {
  const [value, setValue] = useState(radiusKm === null ? '' : String(radiusKm))
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Switching restaurants in the owner page reuses this component, so the input
  // has to follow the selected restaurant rather than keep the first one's value.
  useEffect(() => setValue(radiusKm === null ? '' : String(radiusKm)), [restaurantId, radiusKm])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      // Blank clears the override and returns the restaurant to the default.
      await restaurantsApi.update(restaurantId, {
        delivery_radius_km: value ? Number(value) : null,
      })
      onSaved()
    } catch (err) {
      setError(errorMessage(err, 'Could not update the delivery radius.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="owner-inline-form" onSubmit={submit}>
      {error && <Alert>{error}</Alert>}
      <Field
        label="Delivery radius (km)"
        name="delivery_radius_km"
        type="number"
        min="0.5"
        max="100"
        step="0.5"
        placeholder="Platform default"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <Button variant="ghost" loading={busy}>Save radius</Button>
    </form>
  )
}
