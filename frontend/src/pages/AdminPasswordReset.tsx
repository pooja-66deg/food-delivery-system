import { useState, useEffect } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { request } from "../api/client"
import { useAdminAuth } from "../auth/AdminAuthContext"

interface ResetResponse {
  id: number
  email: string
  role: string
  first_name: string
  last_name: string
  is_active: boolean
}

export function AdminPasswordReset() {
  const [email, setEmail] = useState("")
  const [oldPassword, setOldPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { setAdminToken } = useAdminAuth()

  useEffect(() => {
    if (location.state?.email) {
      setEmail(location.state.email)
    }
    if (location.state?.tempPassword) {
      setOldPassword(location.state.tempPassword)
    }
  }, [location.state])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    if (newPassword !== confirmPassword) {
      setError("Passwords do not match")
      return
    }

    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters")
      return
    }

    setLoading(true)

    try {
      await request<ResetResponse>("/auth/admin/reset-password", {
        method: "POST",
        body: {
          email,
          old_password: oldPassword,
          new_password: newPassword,
        },
      })

      const loginResponse = await request<any>("/auth/admin/login", {
        method: "POST",
        body: { email, password: newPassword },
      })

      setAdminToken(loginResponse.access_token)
      navigate("/admin/dashboard")
    } catch (err: any) {
      setError(err.message || "Password reset failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem 1rem' }}>
      <div style={{ width: '100%', maxWidth: '420px' }}>
        {/* Header */}
        <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
          <h1 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--ink)' }}>
            Reset Password
          </h1>
          <p style={{ fontSize: '0.95rem', color: 'var(--ink-soft)' }}>
            Create a new secure password for your admin account
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
          {/* Email Field (Read-only) */}
          <div className="field">
            <label htmlFor="email">Email Address</label>
            <input
              id="email"
              type="email"
              disabled
              className="input"
              value={email}
              style={{ backgroundColor: 'var(--paper-3)', cursor: 'not-allowed', opacity: 0.6 }}
            />
          </div>

          {/* Current Password Field */}
          <div className="field">
            <label htmlFor="oldPassword">Current Password</label>
            <input
              id="oldPassword"
              type="password"
              required
              className="input"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              disabled={loading}
              placeholder="Your temporary password"
              style={{ cursor: loading ? 'not-allowed' : 'text', opacity: loading ? 0.7 : 1 }}
            />
          </div>

          {/* New Password Field */}
          <div className="field">
            <label htmlFor="newPassword">New Password</label>
            <input
              id="newPassword"
              type="password"
              required
              className="input"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              disabled={loading}
              placeholder="At least 8 characters"
              style={{ cursor: loading ? 'not-allowed' : 'text', opacity: loading ? 0.7 : 1 }}
            />
          </div>

          {/* Confirm Password Field */}
          <div className="field">
            <label htmlFor="confirmPassword">Confirm Password</label>
            <input
              id="confirmPassword"
              type="password"
              required
              className="input"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={loading}
              placeholder="Confirm your new password"
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
                Resetting...
              </>
            ) : (
              'Reset Password'
            )}
          </button>

          {/* Back to Login Link */}
          <div style={{ textAlign: 'center', marginTop: '0.5rem' }}>
            <a href="/admin/login" style={{ fontSize: '0.9rem', fontWeight: 500 }}>
              Back to Login
            </a>
          </div>
        </form>

        {/* Footer */}
        <div style={{ marginTop: '2rem', paddingTop: '1.5rem', borderTop: '1px solid var(--line)', textAlign: 'center' }}>
          <p style={{ fontSize: '0.8rem', color: 'var(--ink-soft)' }}>
            Use a strong password with numbers and special characters
          </p>
        </div>
      </div>
    </div>
  )
}
