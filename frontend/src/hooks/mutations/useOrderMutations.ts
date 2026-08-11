import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ordersApi, PaymentMethod } from '../../api/orders'

/**
 * Hook to create a new order via checkout.
 *
 * Invalidates both the active orders list and cart cache on success,
 * since creating an order clears the cart and affects the orders list.
 *
 * @returns Mutation for creating an order
 */
export function useCreateOrder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (params: { address_id: number; price_hash: string; payment_method?: PaymentMethod }) =>
      ordersApi.checkout(params.address_id, params.price_hash, params.payment_method),
    onSuccess: async () => {
      // Invalidate active orders list and cart cache
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['orders', 'active'] }),
        queryClient.invalidateQueries({ queryKey: ['cart'] }),
      ])
    },
  })
}
