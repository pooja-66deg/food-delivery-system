import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'

import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { BrandPanel } from '../components/BrandPanel'
import { Alert, Button, Field } from '../components/ui'

export function RegisterPage() {
  const navigate = useNavigate()
  const { saveSession } = useAuth()

  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    password: '',
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    void (async () => {
      try {
        await authApi.register(form)
        const tokens = await authApi.login(form.email, form.password)
        await saveSession(tokens)
        navigate('/restaurants')
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Something went wrong.')
      } finally {
        setBusy(false)
      }
    })()
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
          <h2>Create your account</h2>
          <p className="sub">A few details and your first order is minutes away.</p>

          {error && <Alert>{error}</Alert>}

          <form className="form-stack" onSubmit={handleSubmit} style={{ marginTop: error ? '1rem' : 0 }}>
            <div className="form-row">
              <Field
                label="First name"
                name="first_name"
                autoComplete="given-name"
                placeholder="Alex"
                value={form.first_name}
                onChange={set('first_name')}
                required
              />
              <Field
                label="Last name"
                name="last_name"
                autoComplete="family-name"
                placeholder="Rivera"
                value={form.last_name}
                onChange={set('last_name')}
                required
              />
            </div>
            <Field
              label="Email"
              name="email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={form.email}
              onChange={set('email')}
              required
            />
            <Field
              label="Phone"
              name="phone"
              type="tel"
              autoComplete="tel"
              placeholder="+1 555 123 4567"
              value={form.phone}
              onChange={set('phone')}
              required
            />
            <Field
              label="Password"
              name="password"
              type="password"
              autoComplete="new-password"
              placeholder="At least 8 characters"
              value={form.password}
              onChange={set('password')}
              minLength={8}
              required
            />
            <Button type="submit" block loading={busy}>
              Create account
            </Button>
          </form>

          <p className="auth-foot">
            Already have an account? <Link to="/login">Sign in</Link>
          </p>
        </motion.div>
      </main>
    </div>
  )
}
