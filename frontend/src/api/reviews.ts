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
  /** First name plus last initial, e.g. "Alex R.". */
  reviewer_name: string
}

export const reviewsApi = {
  create: (order_id: number, rating: number, comment?: string) =>
    request<Review>('/reviews', { method: 'POST', body: { order_id, rating, comment }, auth: true }),

  // Public: reading ratings is part of choosing a restaurant.
  forRestaurant: (restaurantId: number, limit = 20, offset = 0) =>
    request<Review[]>(`/reviews/restaurant/${restaurantId}?limit=${limit}&offset=${offset}`),
}
