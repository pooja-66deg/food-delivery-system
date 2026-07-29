import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { cartApi } from '../api/cart'
import type { CartView } from '../api/cart'
import { useAuth } from '../auth/AuthContext'

interface CartState {
  cart: CartView | null
  count: number
  refresh: () => Promise<void>
  add: (menuItemId: number, quantity?: number) => Promise<void>
  update: (menuItemId: number, quantity: number) => Promise<void>
  remove: (menuItemId: number) => Promise<void>
  clear: () => Promise<void>
}

const CartContext = createContext<CartState | undefined>(undefined)

function itemCount(cart: CartView | null): number {
  return cart ? cart.items.reduce((sum, i) => sum + i.quantity, 0) : 0
}

export function CartProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated, user } = useAuth()
  const [cart, setCart] = useState<CartView | null>(null)

  // Only customers have a cart; owners/drivers don't.
  const enabled = isAuthenticated && user?.role === 'customer'

  const refresh = useCallback(async () => {
    if (!enabled) {
      setCart(null)
      return
    }
    try {
      setCart(await cartApi.get())
    } catch {
      setCart(null)
    }
  }, [enabled])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const add = useCallback(async (id: number, quantity = 1) => setCart(await cartApi.add(id, quantity)), [])
  const update = useCallback(async (id: number, quantity: number) => setCart(await cartApi.update(id, quantity)), [])
  const remove = useCallback(async (id: number) => setCart(await cartApi.remove(id)), [])
  const clear = useCallback(async () => {
    await cartApi.clear()
    setCart(null)
  }, [])

  const value: CartState = { cart, count: itemCount(cart), refresh, add, update, remove, clear }
  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useCart(): CartState {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error('useCart must be used within CartProvider')
  return ctx
}
