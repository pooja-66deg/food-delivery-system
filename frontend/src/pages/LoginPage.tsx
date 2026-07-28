import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'

import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { BrandPanel } from '../components/BrandPanel'
import { Alert, Button, Field } from '../components/ui'

type Mode = 'password' | 'otp'
type OtpStep = 'request' | 'verify'

export function LoginPage() {
  const navigate = useNavigate()
  const { saveSession } = useAuth()

  const [mode, setMode] = useState<Mode>('password')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // password mode
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  // otp mode
  const [otpStep, setOtpStep] = useState<OtpStep>('request')
  const [phone, setPhone] = useState('')
  const [otp, setOtp] = useState('')
  const [debugOtp, setDebugOtp] = useState<string | null>(null)

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
    setOtpStep('request')
    setDebugOtp(null)
  }

  async function run(action: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
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

  const handleRequestOtp = (e: FormEvent) => {
    e.preventDefault()
    void run(async () => {
      const res = await authApi.requestOtp(phone)
      setDebugOtp(res.debug_otp ?? null)
      setOtpStep('verify')
    })
  }

  const handleVerifyOtp = (e: FormEvent) => {
    e.preventDefault()
    void run(async () => {
      const tokens = await authApi.verifyOtp(phone, otp)
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

          <div className="tabs" style={{ marginBottom: '1.5rem' }}>
            <button className="tab" data-active={mode === 'password'} onClick={() => switchMode('password')}>
              Password
            </button>
            <button className="tab" data-active={mode === 'otp'} onClick={() => switchMode('otp')}>
              One-time code
            </button>
          </div>

          {error && <Alert>{error}</Alert>}

          {mode === 'password' ? (
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
              <Field
                label="Password"
                name="password"
                type="password"
                autoComplete="current-password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <Button type="submit" block loading={busy}>
                Sign in
              </Button>
            </form>
          ) : (
            <div className="form-stack" style={{ marginTop: error ? '1rem' : 0 }}>
              {otpStep === 'request' ? (
                <form className="form-stack" onSubmit={handleRequestOtp}>
                  <Field
                    label="Phone number"
                    name="phone"
                    type="tel"
                    autoComplete="tel"
                    placeholder="+1 555 123 4567"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    required
                  />
                  <Button type="submit" block loading={busy}>
                    Send code
                  </Button>
                </form>
              ) : (
                <form className="form-stack" onSubmit={handleVerifyOtp}>
                  {debugOtp && (
                    <div className="otp-hint">
                      Dev mode: your code is <strong>{debugOtp}</strong>
                    </div>
                  )}
                  <Field
                    label={`Code sent to ${phone}`}
                    name="otp"
                    inputMode="numeric"
                    placeholder="6-digit code"
                    value={otp}
                    onChange={(e) => setOtp(e.target.value)}
                    required
                  />
                  <Button type="submit" block loading={busy}>
                    Verify &amp; sign in
                  </Button>
                  <button
                    type="button"
                    className="link-btn center"
                    onClick={() => {
                      setOtpStep('request')
                      setOtp('')
                      setDebugOtp(null)
                    }}
                  >
                    Use a different number
                  </button>
                </form>
              )}
            </div>
          )}

          <p className="auth-foot">
            New to Tiffin? <Link to="/register">Create an account</Link>
          </p>
        </motion.div>
      </main>
    </div>
  )
}
