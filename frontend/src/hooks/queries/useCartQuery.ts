import { useQuery } from '@tanstack/react-query'
import { cartApi } from '../../api/cart'

export function useCart() {
  return useQuery({
    queryKey: ['cart'],
    queryFn: () => cartApi.get(),
    staleTime: 1000 * 30, // 30 seconds (cart is volatile)
  })
}
