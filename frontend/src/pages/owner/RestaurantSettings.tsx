import { useState } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi, FOOD_TYPE_LABELS } from '../../api/restaurants'
import type { FoodType, RestaurantDetail } from '../../api/restaurants'
import { Alert, Button, FilePicker, Thumb } from '../../components/ui'
import { AddressPanel } from './AddressPanel'
import { DeliveryZonePanel } from './DeliveryZonePanel'
import { OpeningHoursPanel } from './OpeningHoursPanel'

const FOOD_TYPES = Object.keys(FOOD_TYPE_LABELS) as FoodType[]

/**
 * Everything about the restaurant itself — its cover photo, whether it is taking
 * orders, and how far it delivers.
 *
 * Below the menu rather than above it: these are changed now and then, and when
 * they sat at the top an owner scrolled past the photo picker every time they
 * wanted to edit a dish.
 */
export function RestaurantSettings({
  detail,
  onChanged,
}: {
  detail: RestaurantDetail
  /** Refetch, so the header, the row and the dashboard follow a change. */
  onChanged: () => void
}) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function toggleOpen() {
    setBusy(true)
    setError(null)
    try {
      await restaurantsApi.update(detail.id, { is_open: !detail.is_open })
      onChanged()
    } catch (e) {
      setError(errorMessage(e, 'Could not update.'))
    } finally {
      setBusy(false)
    }
  }

  async function setFoodType(food_type: FoodType) {
    setBusy(true)
    setError(null)
    try {
      await restaurantsApi.update(detail.id, { food_type })
      onChanged()
    } catch (e) {
      setError(errorMessage(e, 'Could not update food type.'))
    } finally {
      setBusy(false)
    }
  }

  async function uploadCoverImage(file: File) {
    setError(null)
    try {
      await restaurantsApi.uploadImage(detail.id, file)
      onChanged()
    } catch (err) {
      setError(errorMessage(err, 'Image upload failed.'))
    }
  }

  return (
    <div className="setting-list">
      {error && <Alert>{error}</Alert>}

      {/* Each setting is a labelled row: what it is and why it matters on the
          left, the control on the right. Bare inputs in a column gave an owner
          no way to tell what any of them did. */}
      <div className="setting-row">
        <div className="setting-label">
          <h3>Cover photo</h3>
          <p className="muted">Shown on your card when diners browse.</p>
        </div>
        <div className="setting-control setting-control-image">
          <Thumb url={detail.image_url} alt={`${detail.name} cover`} variant="cover" />
          <FilePicker
            label={detail.image_url ? 'Replace photo' : 'Upload photo'}
            onPick={(file) => void uploadCoverImage(file)}
          />
        </div>
      </div>

      <div className="setting-row">
        <div className="setting-label">
          <h3>Taking orders</h3>
          <p className="muted">
            {detail.is_open
              ? 'Diners can order from you right now.'
              : 'You are hidden from ordering until you reopen.'}
          </p>
        </div>
        <div className="setting-control">
          <span className={`badge ${detail.is_open ? 'badge-open' : 'badge-closed'}`}>
            {detail.is_open ? 'Open' : 'Closed'}
          </span>
          <Button variant="ghost" loading={busy} onClick={() => void toggleOpen()}>
            {detail.is_open ? 'Set closed' : 'Set open'}
          </Button>
        </div>
      </div>

      <div className="setting-row">
        <div className="setting-label">
          <h3>Opening hours</h3>
          <p className="muted">
            Weekly schedule. Optional — leave unset and the switch above alone decides.
            When set, orders are accepted only while you are open and inside these hours.
          </p>
        </div>
        <div className="setting-control setting-control-wide setting-control-hours">
          <OpeningHoursPanel
            restaurantId={detail.id}
            hours={detail.opening_hours ?? []}
            onSaved={onChanged}
          />
        </div>
      </div>

      <div className="setting-row">
        <div className="setting-label">
          <h3>Food type</h3>
          <p className="muted">
            What your kitchen serves. Diners filtering for vegetarian see only restaurants
            set to “Vegetarian” — not ones that merely have vegetarian dishes.
          </p>
        </div>
        <div className="setting-control">
          <select
            className="input"
            aria-label="Food type"
            value={detail.food_type}
            disabled={busy}
            onChange={(e) => void setFoodType(e.target.value as FoodType)}
          >
            {FOOD_TYPES.map((t) => (
              <option key={t} value={t}>
                {FOOD_TYPE_LABELS[t]}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="setting-row">
        <div className="setting-label">
          <h3>Address &amp; contact</h3>
          <p className="muted">
            Where you are and how diners reach you. Changing this does not affect your
            approval — an administrator vetted the business, not the street.
          </p>
        </div>
        <div className="setting-control setting-control-wide">
          <AddressPanel detail={detail} onSaved={onChanged} />
        </div>
      </div>

      <div className="setting-row">
        <div className="setting-label">
          <h3>Delivery range</h3>
          <p className="muted">How far out you will deliver. Blank uses the platform default.</p>
        </div>
        <div className="setting-control">
          <DeliveryZonePanel
            restaurantId={detail.id}
            radiusKm={detail.delivery_radius_km}
            onSaved={onChanged}
          />
        </div>
      </div>
    </div>
  )
}
