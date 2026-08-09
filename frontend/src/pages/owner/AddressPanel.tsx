import { useState } from 'react'
import type { FormEvent } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi } from '../../api/restaurants'
import type { RestaurantDetail } from '../../api/restaurants'
import { AddressAutocomplete } from '../../components/AddressAutocomplete'
import { CityDropdown } from '../../components/CityDropdown'
import { Alert, Button, PhoneField } from '../../components/ui'
import { normalizePhone, PHONE_ERROR } from '../../lib/phone'

/**
 * Where the restaurant is, edited by the owner.
 *
 * The owner's own to change, and it does not re-open approval: an operator
 * vetted the business, not the street it sits on. Moving premises is a normal
 * thing for a restaurant to do and should not take it off the platform.
 *
 * Kept as an explicit save rather than a field-by-field autosave, because a
 * half-typed address that reached delivery would route a driver to nowhere.
 */
export function AddressPanel({
  detail,
  onSaved,
}: {
  detail: RestaurantDetail
  onSaved: () => void
}) {
  const [city, setCity] = useState(detail.city)
  const [addressLine, setAddressLine] = useState(detail.address_line)
  const [phone, setPhone] = useState(detail.phone)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)

  const dirty =
    city !== detail.city || addressLine !== detail.address_line || phone !== detail.phone

  async function submit(e: FormEvent) {
    e.preventDefault()
    const normalized = normalizePhone(phone)
    if (normalized === null) {
      setError(PHONE_ERROR)
      return
    }
    setError(null)
    setSaved(false)
    setBusy(true)
    try {
      await restaurantsApi.update(detail.id, {
        city,
        address_line: addressLine,
        phone: normalized,
      })
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(errorMessage(err, 'Could not save the address.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="owner-form" onSubmit={submit}>
      {error && <Alert>{error}</Alert>}
      {saved && !dirty && <Alert kind="ok">Address saved.</Alert>}

      <CityDropdown value={city} onChange={setCity} required />
      <AddressAutocomplete value={addressLine} onChange={setAddressLine} />
      <PhoneField label="Contact number" name="phone" value={phone} onChange={setPhone} required />

      {/* Disabled until something actually changed, so the button is not a
          no-op that still fires a request and a "saved" message. */}
      <Button loading={busy} disabled={!dirty}>
        Save address
      </Button>
    </form>
  )
}
