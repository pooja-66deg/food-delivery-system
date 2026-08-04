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

/** An outbound attempt, with whether the provider accepted it. */
export interface NotificationDelivery extends Notification {
  delivered: boolean
}

export interface ChannelPreferences {
  email_enabled: boolean
  sms_enabled: boolean
  push_enabled: boolean
}

export const notificationsApi = {
  list: () => request<Notification[]>('/notifications', { auth: true }),

  /** What we tried to send off-app, and whether it landed. */
  deliveries: () =>
    request<NotificationDelivery[]>('/notifications/deliveries', { auth: true }),

  preferences: () =>
    request<ChannelPreferences>('/notifications/preferences', { auth: true }),

  /** Send only the channels being changed; the rest are left alone. */
  updatePreferences: (body: Partial<ChannelPreferences>) =>
    request<ChannelPreferences>('/notifications/preferences', {
      method: 'PATCH',
      body,
      auth: true,
    }),
}
