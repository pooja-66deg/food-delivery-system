import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { useAdminAuth } from "../auth/AdminAuthContext"
import { request } from "../api/client"

interface AdminStats {
  users: number
  restaurants: number
  orders_total: number
  orders_by_status: Record<string, number>
  gross_merchandise_value: number
}

export function AdminPanel() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const { clearAdminToken } = useAdminAuth()
  const navigate = useNavigate()

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await request<AdminStats>("/admin/stats", { auth: true })
        setStats(data)
      } catch (err: any) {
        setError(err.message || "Failed to load stats")
      } finally {
        setLoading(false)
      }
    }
    fetchStats()
  }, [])

  const handleLogout = () => {
    clearAdminToken()
    navigate("/admin/login")
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <h1 className="text-2xl font-bold">Admin Dashboard</h1>
            </div>
            <div className="flex items-center">
              <button
                onClick={handleLogout}
                className="ml-4 px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-red-600 hover:bg-red-700"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        {error && (
          <div className="rounded-md bg-red-50 p-4 mb-4">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {loading ? (
          <div className="text-center py-12">
            <p>Loading stats...</p>
          </div>
        ) : stats ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white overflow-hidden shadow rounded-lg p-6">
              <h3 className="text-gray-500 text-sm font-medium">Total Users</h3>
              <p className="mt-2 text-3xl font-extrabold text-gray-900">{stats.users}</p>
            </div>
            <div className="bg-white overflow-hidden shadow rounded-lg p-6">
              <h3 className="text-gray-500 text-sm font-medium">Total Restaurants</h3>
              <p className="mt-2 text-3xl font-extrabold text-gray-900">{stats.restaurants}</p>
            </div>
            <div className="bg-white overflow-hidden shadow rounded-lg p-6">
              <h3 className="text-gray-500 text-sm font-medium">Total Orders</h3>
              <p className="mt-2 text-3xl font-extrabold text-gray-900">{stats.orders_total}</p>
            </div>
            <div className="bg-white overflow-hidden shadow rounded-lg p-6">
              <h3 className="text-gray-500 text-sm font-medium">GMV</h3>
              <p className="mt-2 text-3xl font-extrabold text-gray-900">
                ${stats.gross_merchandise_value.toFixed(2)}
              </p>
            </div>
          </div>
        ) : null}
      </main>
    </div>
  )
}
