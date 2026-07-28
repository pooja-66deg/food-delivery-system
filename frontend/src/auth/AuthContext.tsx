import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { authApi } from '../api/auth'
import type { Tokens, User } from '../api/auth'
import { setTokenGetter } from '../api/client'

const TOKEN_KEY = 'fd_access_token'
const REFRESH_KEY = 'fd_refresh_token'

interface AuthState {
  user: User | null
  loading: boolean
  isAuthenticated: boolean
  saveSession: (tokens: Tokens) => Promise<void>
  refreshUser: () => Promise<void>
  setUser: (user: User) => void
  logout: () => void
}

const AuthContext = createContext<AuthState | undefined>(undefined)

// The API client reads the token straight from storage on every request.
setTokenGetter(() => localStorage.getItem(TOKEN_KEY))

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshUser = useCallback(async () => {
    if (!localStorage.getItem(TOKEN_KEY)) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      setUser(await authApi.me())
    } catch {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(REFRESH_KEY)
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshUser()
  }, [refreshUser])

  const saveSession = useCallback(
    async (tokens: Tokens) => {
      localStorage.setItem(TOKEN_KEY, tokens.access_token)
      localStorage.setItem(REFRESH_KEY, tokens.refresh_token)
      setLoading(true)
      await refreshUser()
    },
    [refreshUser],
  )

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
    setUser(null)
  }, [])

  const value: AuthState = {
    user,
    loading,
    isAuthenticated: user !== null,
    saveSession,
    refreshUser,
    setUser,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
