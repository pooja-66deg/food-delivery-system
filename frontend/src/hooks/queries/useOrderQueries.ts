import { useQuery } from '@tanstack/react-query'
import { ordersApi, OrderScope } from '../../api/orders'

/**
 * Hook to fetch a list of orders for the current user.
 *
 * @param scope - Which slice of the customer's history to list: 'active', 'past', or 'all' (default: 'all')
 * @returns Query for OrderSummary[]
 *
 * Note: Orders change frequently, so staleTime is 1 minute instead of the default 5 minutes.
 */
export function useOrderList(scope: OrderScope = 'all') {
  return useQuery({
    queryKey: ['orders', 'list', scope],
    queryFn: () => ordersApi.list(scope),
    staleTime: 1000 * 60, // 1 minute (orders are volatile)
  })
}

/**
 * Hook to fetch a single order by ID.
 *
 * @param id - The order ID to fetch
 * @returns Query for Order
 *
 * Note: Orders change frequently, so staleTime is 1 minute instead of the default 5 minutes.
 */
export function useOrder(id: number) {
  return useQuery({
    queryKey: ['orders', 'detail', id],
    queryFn: () => ordersApi.get(id),
    staleTime: 1000 * 60, // 1 minute (orders are volatile)
    enabled: !!id, // Only fetch if id is provided
  })
}
