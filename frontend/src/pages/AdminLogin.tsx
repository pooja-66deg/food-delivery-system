import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { errorMessage, request } from "../api/client"
import { useAdminAuth } from "../auth/AdminAuthContext"

interface LoginResponse {
  access_token?: string
  token_type?: string
  detail?: string
  password_reset_required?: boolean
  email?: string
}

const GATE_SESSION_KEY = "admin_gate_unlocked"

interface GateStatus {
  gate_required: boolean
}

export function AdminLogin() {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [gatePassword, setGatePassword] = useState("")
  const [error, setError] = useState("")
  const [gateError, setGateError] = useState("")
  const [loading, setLoading] = useState(false)
  const [gateChecking, setGateChecking] = useState(false)
  const [gateUnlocked, setGateUnlocked] = useState<boolean | undefined>(undefined)
  const navigate = useNavigate()
  const { setAdminToken } = useAdminAuth()

  useEffect(() => {
    let cancelled = false

    if (sessionStorage.getItem(GATE_SESSION_KEY) === "true") {
      setGateUnlocked(true)
      return
    }

    request<GateStatus>("/auth/admin/gate")
      .then((status) => {
        if (!cancelled) setGateUnlocked(!status.gate_required)
      })
      .catch(() => {
        if (!cancelled) setGateUnlocked(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const handleGateSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setGateError("")
    setGateChecking(true)

    try {
      await request("/auth/admin/gate", {
        method: "POST",
        body: { password: gatePassword },
      })
      sessionStorage.setItem(GATE_SESSION_KEY, "true")
      setGateUnlocked(true)
      setGatePassword("")
    } catch (err: unknown) {
      setGateError(errorMessage(err, "Incorrect password"))
      setGatePassword("")
    } finally {
      setGateChecking(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      const response = await request<LoginResponse>("/auth/admin/login", {
        method: "POST",
        body: { email, password },
      })

      if (response.access_token) {
        setAdminToken(response.access_token)
        navigate("/admin/dashboard")
      }
    } catch (err: any) {
      if (err.status === 403 && err.details?.password_reset_required) {
        navigate("/admin/reset-password", { state: { email, tempPassword: password } })
      } else {
        setError(err.message || "Login failed")
      }
    } finally {
      setLoading(false)
    }
  }

  if (gateUnlocked === undefined) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem 1rem' }}>
        <p style={{ fontSize: '0.9rem', color: 'var(--ink-soft)' }}>Loading…</p>
      </div>
    )
  }

  // Show password gate first
  if (!gateUnlocked) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem 1rem' }}>
        <div style={{ width: '100%', maxWidth: '380px' }}>
          {/* Gate Header */}
          <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
            <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>🔒</div>
            <h1 style={{ fontSize: '1.8rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--ink)' }}>
              Access Restricted
            </h1>
            <p style={{ fontSize: '0.9rem', color: 'var(--ink-soft)' }}>
              Enter password to access admin panel
            </p>
          </div>

          {/* Gate Error */}
          {gateError && (
            <div className="alert alert-error" style={{ marginBottom: '1.5rem' }}>
              <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" style={{ flexShrink: 0 }}>
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              <div>
                <p>{gateError}</p>
              </div>
            </div>
          )}

          {/* Gate Form */}
          <form onSubmit={handleGateSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
            <div className="field">
              <label htmlFor="gatePassword">Gate Password</label>
              <input
                id="gatePassword"
                type="password"
                required
                className="input"
                value={gatePassword}
                onChange={(e) => setGatePassword(e.target.value)}
                placeholder="Enter access password"
                disabled={gateChecking}
                autoFocus
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary btn-block"
              disabled={gateChecking}
            >
              {gateChecking ? "Checking…" : "Unlock Access"}
            </button>
          </form>

          {/* Footer */}
          <div style={{ marginTop: '2rem', paddingTop: '1.5rem', borderTop: '1px solid var(--line)', textAlign: 'center' }}>
            <p style={{ fontSize: '0.8rem', color: 'var(--ink-soft)' }}>
              Protected admin area
            </p>
          </div>
        </div>
      </div>
    )
  }

  // Show login form after gate is unlocked
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem 1rem' }}>
      <div style={{ width: '100%', maxWidth: '420px' }}>
        {/* Header */}
        <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
          <h1 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--ink)' }}>
            Admin Login
          </h1>
          <p style={{ fontSize: '0.95rem', color: 'var(--ink-soft)' }}>
            Manage your food delivery platform
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="alert alert-error" style={{ marginBottom: '1.5rem' }}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" style={{ flexShrink: 0 }}>
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <div>
              <p>{error}</p>
            </div>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
          {/* Email Field */}
          <div className="field">
            <label htmlFor="email">Email Address</label>
            <input
              id="email"
              name="email"
              type="email"
              required
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
              placeholder="admin@example.com"
              style={{ cursor: loading ? 'not-allowed' : 'text', opacity: loading ? 0.7 : 1 }}
            />
          </div>

          {/* Password Field */}
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              required
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              placeholder="••••••••"
              style={{ cursor: loading ? 'not-allowed' : 'text', opacity: loading ? 0.7 : 1 }}
            />
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary btn-block"
            style={{ marginTop: '0.5rem', opacity: loading ? 0.7 : 1, cursor: loading ? 'not-allowed' : 'pointer' }}
          >
            {loading ? (
              <>
                <span className="spin" />
                Signing in...
              </>
            ) : (
              'Sign In'
            )}
          </button>

          {/* Forgot Password Link */}
          <div style={{ textAlign: 'center', marginTop: '0.5rem' }}>
            <a href="/admin/reset-password" style={{ fontSize: '0.9rem', fontWeight: 500 }}>
              Forgot your password?
            </a>
          </div>
        </form>

        {/* Footer */}
        <div style={{ marginTop: '2rem', paddingTop: '1.5rem', borderTop: '1px solid var(--line)', textAlign: 'center' }}>
          <p style={{ fontSize: '0.8rem', color: 'var(--ink-soft)' }}>
            Protected admin area. Authorized access only.
          </p>
        </div>
      </div>
    </div>
  )
}
