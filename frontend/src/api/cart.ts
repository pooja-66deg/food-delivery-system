// Typed bindings for the cart domain.

import { request } from './client'

export interface CartItem {
  menu_item_id: number
  name: string
  unit_price: number
  quantity: number
  line_total: number
}

export interface CartView {
  restaurant_id: number | null
  items: CartItem[]
  subtotal: number
  price_hash: string
}

/** A refilled cart, plus the lines that could not be carried over. */
export interface ReorderResult {
  cart: CartView
  /** "name — reason" per skipped line, e.g. "Salad — sold out". */
  skipped: string[]
}

export const cartApi = {
  get: () => request<CartView>('/cart', { auth: true }),

  add: (menu_item_id: number, quantity = 1) =>
    request<CartView>('/cart/items', { method: 'POST', body: { menu_item_id, quantity }, auth: true }),

  update: (menuItemId: number, quantity: number) =>
    request<CartView>(`/cart/items/${menuItemId}`, { method: 'PATCH', body: { quantity }, auth: true }),

  remove: (menuItemId: number) =>
    request<CartView>(`/cart/items/${menuItemId}`, { method: 'DELETE', auth: true }),

  clear: () => request<void>('/cart', { method: 'DELETE', auth: true }),

  /**
   * Refill the cart from a past order, replacing whatever is in it.
   *
   * Succeeds even when some lines can no longer be ordered — those come back in
   * `skipped`, so the caller must show them rather than assume a clean refill.
   */
  reorder: (orderId: number) =>
    request<ReorderResult>('/cart/reorder', {
      method: 'POST',
      body: { order_id: orderId },
      auth: true,
    }),
}
