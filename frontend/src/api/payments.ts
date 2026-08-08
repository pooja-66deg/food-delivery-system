// Typed bindings for the payments domain.

import { request } from './client'
import type { Payment } from './orders'

export type { Payment }

export const paymentsApi = {
  history: () => request<Payment[]>('/payments', { auth: true }),
  forOrder: (orderId: number) => request<Payment>(`/payments/order/${orderId}`, { auth: true }),
  /** Open (or reopen) the hosted card page for an order awaiting payment.
   *
   *  Also how checkout gets its Stripe URL now. The payment is created by the
   *  payments service when it reads the order event, so it cannot be in the
   *  checkout response — this is polled for it instead, and 404s until that
   *  event has landed. */
  resume: (orderId: number) =>
    request<Payment>(`/payments/order/${orderId}/resume`, { method: 'POST', auth: true }),

  retry: (orderId: number) =>
    request<Payment>(`/payments/order/${orderId}/retry`, { method: 'POST', auth: true }),
  /** Settle an order the customer has just been redirected back from. */
  confirm: (orderId: number) =>
    request<Payment>(`/payments/order/${orderId}/confirm`, { method: 'POST', auth: true }),
}
