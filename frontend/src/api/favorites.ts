// Typed bindings for favourite restaurants.

import { request } from './client'
import type { Restaurant } from './restaurants'

export const favoritesApi = {
  /** Saved restaurants in full, most recently saved first. */
  list: () => request<Restaurant[]>('/favorites', { auth: true }),

  /** Ids only — enough for a browse page to fill in the saved hearts. */
  ids: () => request<number[]>('/favorites/ids', { auth: true }),

  /** Idempotent: saving an already-saved restaurant is not an error. */
  add: (restaurantId: number) =>
    request<void>('/favorites', {
      method: 'POST',
      body: { restaurant_id: restaurantId },
      auth: true,
    }),

  remove: (restaurantId: number) =>
    request<void>(`/favorites/${restaurantId}`, { method: 'DELETE', auth: true }),
}
