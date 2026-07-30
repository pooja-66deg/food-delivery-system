import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'

import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { BrandPanel } from '../components/BrandPanel'
import { Alert, Button, Field } from '../components/ui'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [debugToken, setDebugToken] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await authApi.forgotPassword(email)
      setDebugToken(res.debug_token ?? null)
      setSent(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-split">
      <BrandPanel />
      <main className="auth-form-panel">
        <motion.div
          className="auth-card"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        >
          <h2>Reset your password</h2>
          <p className="sub">Enter your email and we'll send a reset link.</p>

          {error && <Alert>{error}</Alert>}

          {sent ? (
            <>
              <Alert kind="ok">If an account exists for that email, a reset link is on its way.</Alert>
              {debugToken && (
                <div className="otp-hint" style={{ marginTop: '1rem' }}>
                  Dev mode:{' '}
                  <Link to={`/reset-password?token=${encodeURIComponent(debugToken)}`}>
                    continue to reset
                  </Link>
                </div>
              )}
              <p className="sub" style={{ marginTop: '1.5rem' }}>
                <Link to="/login" className="back-link">← Back to sign in</Link>
              </p>
            </>
          ) : (
            <form className="form-stack" onSubmit={handleSubmit} style={{ marginTop: error ? '1rem' : 0 }}>
              <Field
                label="Email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              <Button type="submit" block loading={busy}>Send reset link</Button>
              <p className="sub" style={{ textAlign: 'center' }}>
                <Link to="/login" className="back-link">← Back to sign in</Link>
              </p>
            </form>
          )}
        </motion.div>
      </main>
    </div>
  )
}
