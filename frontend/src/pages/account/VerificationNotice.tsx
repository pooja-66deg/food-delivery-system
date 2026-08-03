import { useState } from 'react'

import { authApi } from '../../api/auth'
import { errorMessage } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import { Alert, Button } from '../../components/ui'

/**
 * Advisory only — nothing on the platform is gated on a verified address, so
 * this informs rather than blocks.
 */
export function VerificationNotice() {
  const { user } = useAuth()
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)

  if (!user) return null

  if (user.is_email_verified) {
    return (
      <p className="muted" style={{ marginBottom: '1.25rem' }}>
        <span className="chip chip-accent">Email verified</span>
      </p>
    )
  }

  const send = () => {
    setBusy(true)
    setMsg(null)
    void (async () => {
      try {
        await authApi.requestEmailVerification()
        setMsg({ kind: 'ok', text: `Verification link sent to ${user.email}.` })
      } catch (err) {
        setMsg({ kind: 'error', text: errorMessage(err, 'Could not send the verification email.') })
      } finally {
        setBusy(false)
      }
    })()
  }

  return (
    <section className="card panel" style={{ marginBottom: '1.25rem' }}>
      <h3>Verify your email</h3>
      <p className="muted">
        <strong>{user.email}</strong> has not been confirmed yet. Verifying it lets us reach you
        about your orders.
      </p>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <div style={{ marginTop: '1rem' }}>
        <Button type="button" onClick={send} loading={busy}>
          Send verification email
        </Button>
      </div>
    </section>
  )
}
