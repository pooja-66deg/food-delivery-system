import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'

import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { BrandPanel } from '../components/BrandPanel'
import { Alert, Button, Field, PasswordField } from '../components/ui'

export function ResetPasswordPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [token, setToken] = useState(params.get('token') ?? '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await authApi.resetPassword(token, password)
      setDone(true)
      setTimeout(() => navigate('/login'), 1500)
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
          <h2>Choose a new password</h2>
          <p className="sub">Enter the reset token and your new password.</p>

          {error && <Alert>{error}</Alert>}

          {done ? (
            <Alert kind="ok">Password updated. Redirecting to sign in…</Alert>
          ) : (
            <form className="form-stack" onSubmit={handleSubmit} style={{ marginTop: error ? '1rem' : 0 }}>
              <Field
                label="Reset token"
                name="token"
                placeholder="Paste your reset token"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                required
              />
              <PasswordField
                label="New password"
                name="new_password"
                autoComplete="new-password"
                placeholder="••••••••"
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <Button type="submit" block loading={busy}>Update password</Button>
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
