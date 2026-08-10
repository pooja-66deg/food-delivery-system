import { createContext, useCallback, useContext, useState } from 'react'
import type { ReactNode } from 'react'

const ADMIN_TOKEN_KEY = 'fd_admin_token'

interface AdminAuthState {
  adminToken: string | null
  isAuthenticated: boolean
  setAdminToken: (token: string) => void
  clearAdminToken: () => void
}

const AdminAuthContext = createContext<AdminAuthState | undefined>(undefined)

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [adminToken, setAdminTokenState] = useState<string | null>(
    localStorage.getItem(ADMIN_TOKEN_KEY),
  )

  const setAdminToken = useCallback((token: string) => {
    localStorage.setItem(ADMIN_TOKEN_KEY, token)
    setAdminTokenState(token)
  }, [])

  const clearAdminToken = useCallback(() => {
    localStorage.removeItem(ADMIN_TOKEN_KEY)
    setAdminTokenState(null)
  }, [])

  const value: AdminAuthState = {
    adminToken,
    isAuthenticated: adminToken !== null,
    setAdminToken,
    clearAdminToken,
  }

  return (
    <AdminAuthContext.Provider value={value}>{children}</AdminAuthContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAdminAuth(): AdminAuthState {
  const ctx = useContext(AdminAuthContext)
  if (!ctx) throw new Error('useAdminAuth must be used within AdminAuthProvider')
  return ctx
}
