import { useMutation, useQueryClient } from '@tanstack/react-query'
import { favoritesApi } from '../../api/favorites'

/**
 * Hook to toggle the favorite status of a restaurant.
 *
 * Automatically invalidates all favorites-related queries on success
 * to keep the UI in sync with server state.
 */
export function useToggleFavorite() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      restaurantId,
      isFavorite,
    }: {
      restaurantId: number
      isFavorite: boolean
    }) => {
      if (isFavorite) {
        // Currently favorited, so remove it
        await favoritesApi.remove(restaurantId)
      } else {
        // Not currently favorited, so add it
        await favoritesApi.add(restaurantId)
      }
    },
    onSuccess: () => {
      // Invalidate all favorites-related queries to refresh the UI
      queryClient.invalidateQueries({ queryKey: ['favorites'] })
    },
  })
}
