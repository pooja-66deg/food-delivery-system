import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'

import { authApi } from '../api/auth'
import { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { BrandPanel } from '../components/BrandPanel'
import { Alert, Button, Field, PasswordField } from '../components/ui'

export function LoginPage() {
  const navigate = useNavigate()
  const { saveSession } = useAuth()

  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  async function run(action: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(errorMessage(err, 'Something went wrong.'))
    } finally {
      setBusy(false)
    }
  }

  const handlePassword = (e: FormEvent) => {
    e.preventDefault()
    void run(async () => {
      const tokens = await authApi.login(email, password)
      await saveSession(tokens)
      navigate('/restaurants')
    })
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
          <h2>Welcome back</h2>
          <p className="sub">Sign in to pick up where you left off.</p>

          {error && <Alert>{error}</Alert>}

          <form className="form-stack" onSubmit={handlePassword} style={{ marginTop: error ? '1rem' : 0 }}>
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
            <PasswordField
              label="Password"
              name="password"
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <Button type="submit" block loading={busy}>
              Sign in
            </Button>
            <p className="sub" style={{ textAlign: 'center' }}>
              <Link to="/forgot-password" className="back-link">Forgot password?</Link>
            </p>
          </form>

          <p className="auth-foot">
            New to Tiffin? <Link to="/register">Create an account</Link>
          </p>
        </motion.div>
      </main>
    </div>
  )
}
