import { useState } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi } from '../../api/restaurants'
import type { RestaurantDetail } from '../../api/restaurants'
import { Alert, Button, FilePicker, Thumb } from '../../components/ui'
import { DeliveryZonePanel } from './DeliveryZonePanel'

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
