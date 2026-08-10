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
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            Reset Password
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Please set a new password for your admin account
          </p>
        </div>
        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {error && (
            <div className="rounded-md bg-red-50 p-4">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}
          <div className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                Email
              </label>
              <input
                id="email"
                type="email"
                disabled
                value={email}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 bg-gray-100 text-gray-900 sm:text-sm"
              />
            </div>
            <div>
              <label htmlFor="oldPassword" className="block text-sm font-medium text-gray-700">
                Current Password
              </label>
              <input
                id="oldPassword"
                type="password"
                required
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                placeholder="Your temporary password"
              />
            </div>
            <div>
              <label htmlFor="newPassword" className="block text-sm font-medium text-gray-700">
                New Password
              </label>
              <input
                id="newPassword"
                type="password"
                required
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                placeholder="At least 8 characters"
              />
            </div>
            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700">
                Confirm Password
              </label>
              <input
                id="confirmPassword"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                placeholder="Confirm your new password"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
          >
            {loading ? "Resetting..." : "Reset Password"}
          </button>
        </form>
      </div>
    </div>
  )
}
