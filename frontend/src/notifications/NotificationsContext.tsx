import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { notificationsApi } from '../api/notifications'
import { useAuth } from '../auth/AuthContext'

const SEEN_KEY = 'fd_notif_seen_at'
const POLL_MS = 25000

interface NotificationsState {
  unread: number
  refresh: () => Promise<void>
  markAllSeen: () => void
}

const NotificationsContext = createContext<NotificationsState | undefined>(undefined)

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth()
  const [unread, setUnread] = useState(0)

  const refresh = useCallback(async () => {
    if (!isAuthenticated) {
      setUnread(0)
      return
    }
    try {
      const items = await notificationsApi.list()
      const seenAt = Number(localStorage.getItem(SEEN_KEY) ?? 0)
      setUnread(items.filter((n) => new Date(n.created_at).getTime() > seenAt).length)
    } catch {
      /* ignore transient errors; keep last known count */
    }
  }, [isAuthenticated])

  // Poll while authenticated so new notifications surface without a page load.
  useEffect(() => {
    void refresh()
    if (!isAuthenticated) return
    const timer = setInterval(() => void refresh(), POLL_MS)
    return () => clearInterval(timer)
  }, [refresh, isAuthenticated])

  const markAllSeen = useCallback(() => {
    localStorage.setItem(SEEN_KEY, String(Date.now()))
    setUnread(0)
  }, [])

  return (
    <NotificationsContext.Provider value={{ unread, refresh, markAllSeen }}>
      {children}
    </NotificationsContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useNotifications(): NotificationsState {
  const ctx = useContext(NotificationsContext)
  if (!ctx) throw new Error('useNotifications must be used within NotificationsProvider')
  return ctx
}
