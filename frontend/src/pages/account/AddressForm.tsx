import { useState } from 'react'
import type { FormEvent } from 'react'

import type { AddressInput } from '../../api/auth'
import { Button, Field } from '../../components/ui'
import { AddressAutocomplete } from '../../components/AddressAutocomplete'
import { CityDropdown } from '../../components/CityDropdown'

export const EMPTY_ADDRESS: AddressInput = {
  label: 'home',
  line1: '',
  line2: '',
  city: '',
  postal_code: '',
  is_default: false,
}

interface AddressFormProps {
  /** Prefill — the address being edited, or EMPTY_ADDRESS when adding. */
  initial: AddressInput
  submitLabel: string
  busy: boolean
  onSubmit: (values: AddressInput) => void
  onCancel: () => void
}

/** One form for both adding and editing, so the two paths cannot drift apart. */
export function AddressForm({ initial, submitLabel, busy, onSubmit, onCancel }: AddressFormProps) {
  const [form, setForm] = useState<AddressInput>(initial)

  const set = (key: keyof AddressInput) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit(form)
  }

  return (
    <form className="form-stack" onSubmit={submit} style={{ marginBottom: '1.25rem' }}>
      <Field label="Label" name="label" placeholder="home, work…" value={form.label} onChange={set('label')} required />
      <AddressAutocomplete
        value={form.line1}
        onChange={(line1) => setForm({ ...form, line1 })}
        placeholder="Start typing your address..."
      />
      <Field label="Address line 2" name="line2" placeholder="Apt, suite (optional)" value={form.line2 ?? ''} onChange={set('line2')} />
      <div className="form-row">
        <div style={{ flex: 1 }}>
          <CityDropdown
            value={form.city}
            onChange={(city) => setForm({ ...form, city })}
            required
          />
        </div>
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
      <div className="form-row">
        <Button type="submit" loading={busy}>
          {submitLabel}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
