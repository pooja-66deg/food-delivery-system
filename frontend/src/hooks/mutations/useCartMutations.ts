import { useMutation } from '@tanstack/react-query'
import { cartApi } from '../../api/cart'
import { useInvalidateCart } from './invalidateCart'

/**
 * Add an item to the cart.
 * Invalidates the cart query on success to fetch updated cart data.
 */
export function useAddToCart() {
  const invalidateCart = useInvalidateCart()
  return useMutation({
    mutationFn: (variables: { menu_item_id: number; quantity?: number }) =>
      cartApi.add(variables.menu_item_id, variables.quantity),
    onSuccess: invalidateCart,
  })
}

/**
 * Update the quantity of an item in the cart.
 * Invalidates the cart query on success to fetch updated cart data.
 */
export function useUpdateCartItem() {
  const invalidateCart = useInvalidateCart()
  return useMutation({
    mutationFn: (variables: { menuItemId: number; quantity: number }) =>
      cartApi.update(variables.menuItemId, variables.quantity),
    onSuccess: invalidateCart,
  })
}

/**
 * Remove an item from the cart.
 * Invalidates the cart query on success to fetch updated cart data.
 */
export function useRemoveFromCart() {
  const invalidateCart = useInvalidateCart()
  return useMutation({
    mutationFn: (menuItemId: number) => cartApi.remove(menuItemId),
    onSuccess: invalidateCart,
  })
}

/**
 * Clear all items from the cart.
 * Invalidates the cart query on success to fetch updated cart data.
 */
export function useClearCart() {
  const invalidateCart = useInvalidateCart()
  return useMutation({
    mutationFn: () => cartApi.clear(),
    onSuccess: invalidateCart,
  })
}
