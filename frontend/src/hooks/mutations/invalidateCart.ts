import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'

/**
 * Hook that returns a function to invalidate the cart query.
 * Use in mutation onSuccess callbacks to refresh cart data after mutations.
 */
export function useInvalidateCart() {
  const queryClient = useQueryClient()
  return useCallback(() => queryClient.invalidateQueries({ queryKey: ['cart'] }), [queryClient])
}
