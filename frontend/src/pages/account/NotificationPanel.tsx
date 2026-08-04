import { useEffect, useState } from 'react'

import { errorMessage } from '../../api/client'
import { notificationsApi } from '../../api/notifications'
import type { ChannelPreferences } from '../../api/notifications'
import { Alert, Loading } from '../../components/ui'

type Channel = keyof ChannelPreferences

const CHANNELS: { key: Channel; label: string; hint: string }[] = [
  { key: 'email_enabled', label: 'Email', hint: 'Confirmations and the final outcome of an order.' },
  { key: 'sms_enabled', label: 'SMS', hint: 'A text when your order sets off, arrives, or is cancelled.' },
  { key: 'push_enabled', label: 'Push', hint: 'Every step of an order, on devices you have signed in on.' },
]

/**
 * Choose which channels order updates go out on.
 *
 * Each toggle saves on its own rather than behind a Save button: there is one
 * field per row, so a button would only add a step. The switch is set from the
 * server's response, so a rejected change visibly snaps back instead of showing
 * a state that was never stored.
 */
export function NotificationPanel() {
  const [prefs, setPrefs] = useState<ChannelPreferences | null>(null)
  const [saving, setSaving] = useState<Channel | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        setPrefs(await notificationsApi.preferences())
      } catch (err) {
        setError(errorMessage(err, 'Could not load your notification settings.'))
      }
    })()
  }, [])

  async function toggle(key: Channel, next: boolean) {
    setError(null)
    setSaving(key)
    try {
      setPrefs(await notificationsApi.updatePreferences({ [key]: next }))
    } catch (err) {
      setError(errorMessage(err, 'Could not save that change.'))
    } finally {
      setSaving(null)
    }
  }

  return (
    <section className="card panel">
      <h3>Order updates</h3>
      {error && <Alert>{error}</Alert>}
      {!prefs ? (
        <Loading />
      ) : (
        <ul className="pref-list">
          {CHANNELS.map(({ key, label, hint }) => (
            <li key={key} className="pref-row">
              <label htmlFor={key}>
                <span className="pref-label">{label}</span>
                <span className="muted">{hint}</span>
              </label>
              <input
                id={key}
                type="checkbox"
                checked={prefs[key]}
                disabled={saving !== null}
                onChange={(e) => void toggle(key, e.target.checked)}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
