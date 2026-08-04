// Typed bindings for the reviews domain.

import { request } from './client'

export interface Review {
  id: number
  order_id: number
  customer_id: number
  restaurant_id: number
  rating: number
  comment: string | null
  created_at: string
  /** Null means never edited — not "edited when created". */
  updated_at: string | null
  /** The restaurant's public answer, if they have given one. */
  owner_reply: string | null
  owner_replied_at: string | null
  /** First name plus last initial, e.g. "Alex R.". */
  reviewer_name: string
}

export const reviewsApi = {
  create: (order_id: number, rating: number, comment?: string) =>
    request<Review>('/reviews', { method: 'POST', body: { order_id, rating, comment }, auth: true }),

  // Public: reading ratings is part of choosing a restaurant.
  forRestaurant: (restaurantId: number, limit = 20, offset = 0) =>
    request<Review[]>(`/reviews/restaurant/${restaurantId}?limit=${limit}&offset=${offset}`),

  /**
   * Revise your own review. Omitting `comment` leaves it alone; passing null
   * clears it — so the two cases must stay distinguishable here too.
   */
  update: (reviewId: number, body: { rating?: number; comment?: string | null }) =>
    request<Review>(`/reviews/${reviewId}`, { method: 'PATCH', body, auth: true }),

  remove: (reviewId: number) =>
    request<void>(`/reviews/${reviewId}`, { method: 'DELETE', auth: true }),

  /** Owner-only. Replying again replaces the previous answer. */
  reply: (reviewId: number, reply: string) =>
    request<Review>(`/reviews/${reviewId}/reply`, { method: 'POST', body: { reply }, auth: true }),
}
