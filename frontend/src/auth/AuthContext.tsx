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
  replaceTokens: (tokens: Tokens) => void
  logout: () => Promise<void>
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

  /** Swap in a pair the server minted mid-session (e.g. after a password
   * change, which invalidates every earlier token). */
  const replaceTokens = useCallback((tokens: Tokens) => {
    localStorage.setItem(TOKEN_KEY, tokens.access_token)
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token)
  }, [])

  const logout = useCallback(async () => {
    const refresh = localStorage.getItem(REFRESH_KEY)
    try {
      // Revokes both tokens server-side. Dropping them locally is not enough:
      // a copied token would stay valid until it expired on its own.
      if (refresh) await authApi.logout(refresh)
    } catch {
      // A failed call must never strand the user signed in — clear regardless.
    } finally {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(REFRESH_KEY)
      setUser(null)
    }
  }, [])

  const value: AuthState = {
    user,
    loading,
    isAuthenticated: user !== null,
    saveSession,
    refreshUser,
    setUser,
    replaceTokens,
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
