// Typed bindings for the notifications domain.

import { request } from './client'

export interface Notification {
  id: number
  channel: string
  type: string
  message: string
  order_id: number | null
  created_at: string
}

export const notificationsApi = {
  list: () => request<Notification[]>('/notifications', { auth: true }),
}
