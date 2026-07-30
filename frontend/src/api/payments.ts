// Typed bindings for the payments domain.

import { request } from './client'
import type { Payment } from './orders'

export type { Payment }

export const paymentsApi = {
  history: () => request<Payment[]>('/payments', { auth: true }),
  forOrder: (orderId: number) => request<Payment>(`/payments/order/${orderId}`, { auth: true }),
  retry: (orderId: number) =>
    request<Payment>(`/payments/order/${orderId}/retry`, { method: 'POST', auth: true }),
}
