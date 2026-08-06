import { describe, expect, it } from 'vitest'

import type { Order } from '../../../src/api/orders'
import type { RestaurantDetail } from '../../../src/api/restaurants'
import {
  dishCount,
  isLiveOrder,
  isSameDay,
  lowStockCount,
  orderValueToday,
  plural,
  timeAgo,
} from '../../../src/pages/owner/ownerStats'

const NOW = new Date('2026-08-06T14:00:00')

const order = (fields: Partial<Order>) =>
  ({ id: 1, status: 'PAYMENT_SUCCESS', total: 10, created_at: NOW.toISOString(), ...fields }) as Order

/** A detail carrying just the menu shape these helpers read. */
const detail = (stocks: (number | null)[][]) =>
  ({
    menu: stocks.map((items, c) => ({
      id: c,
      name: `Cat ${c}`,
      sort_order: c,
      items: items.map((stock_quantity, i) => ({ id: i, stock_quantity })),
    })),
  }) as RestaurantDetail

describe('isLiveOrder', () => {
  it('counts what the kitchen still owes', () => {
    for (const status of ['PAYMENT_SUCCESS', 'RESTAURANT_ACCEPTED', 'PREPARING', 'READY_FOR_PICKUP']) {
      expect(isLiveOrder(order({ status }))).toBe(true)
    }
  })

  it('stops once a driver has it — that is no longer the kitchen’s to act on', () => {
    expect(isLiveOrder(order({ status: 'OUT_FOR_DELIVERY' }))).toBe(false)
  })

  it('excludes finished and dead orders', () => {
    for (const status of ['DELIVERED', 'COMPLETED', 'CANCELLED', 'REJECTED', 'PAYMENT_PENDING']) {
      expect(isLiveOrder(order({ status }))).toBe(false)
    }
  })
})

describe('isSameDay', () => {
  it('matches the same calendar day', () => {
    expect(isSameDay('2026-08-06T01:00:00', NOW)).toBe(true)
  })

  it('rejects the day before, not just a 24-hour window', () => {
    expect(isSameDay('2026-08-05T23:00:00', NOW)).toBe(false)
  })

  it('rejects the same day of an adjacent month', () => {
    expect(isSameDay('2026-07-06T14:00:00', NOW)).toBe(false)
  })
})

describe('orderValueToday', () => {
  it('sums today’s takings', () => {
    const total = orderValueToday([order({ total: 22.5 }), order({ id: 2, total: 10 })], NOW)

    expect(total).toBe(32.5)
  })

  it('leaves out cancelled, rejected and unpaid orders', () => {
    const orders = [
      order({ total: 10 }),
      order({ id: 2, total: 99, status: 'CANCELLED' }),
      order({ id: 3, total: 99, status: 'REJECTED' }),
      order({ id: 4, total: 99, status: 'PAYMENT_PENDING' }),
    ]

    expect(orderValueToday(orders, NOW)).toBe(10)
  })

  it('leaves out yesterday', () => {
    const orders = [order({ total: 10 }), order({ id: 2, total: 99, created_at: '2026-08-05T14:00:00' })]

    expect(orderValueToday(orders, NOW)).toBe(10)
  })

  it('is zero, not NaN, with no orders', () => {
    expect(orderValueToday([], NOW)).toBe(0)
  })
})

describe('lowStockCount', () => {
  it('counts items at or under the threshold across every category', () => {
    expect(lowStockCount(detail([[0, 3], [4, 1]]))).toBe(3)
  })

  it('treats untracked stock as unknown, not low', () => {
    expect(lowStockCount(detail([[null, null]]))).toBe(0)
  })

  it('counts zero as low — sold out is the worst case, not an absence', () => {
    expect(lowStockCount(detail([[0]]))).toBe(1)
  })
})

describe('dishCount', () => {
  it('totals items across categories', () => {
    expect(dishCount(detail([[1, 2], [3]]))).toBe(3)
  })

  it('is zero for a menu with no items', () => {
    expect(dishCount(detail([[]]))).toBe(0)
  })
})

describe('timeAgo', () => {
  const at = (ms: number) => new Date(NOW.getTime() - ms).toISOString()

  it('says just now under a minute', () => {
    expect(timeAgo(at(30_000), NOW)).toBe('just now')
  })

  it('keeps minutes for anything under an hour, so urgency survives', () => {
    expect(timeAgo(at(3 * 60_000), NOW)).toBe('3 min ago')
    expect(timeAgo(at(59 * 60_000), NOW)).toBe('59 min ago')
  })

  it('moves to hours, then days', () => {
    expect(timeAgo(at(2 * 3_600_000), NOW)).toBe('2 hr ago')
    expect(timeAgo(at(26 * 3_600_000), NOW)).toBe('yesterday')
    expect(timeAgo(at(3 * 24 * 3_600_000), NOW)).toBe('3 days ago')
  })
})

describe('plural', () => {
  it('keeps the singular at one', () => {
    expect(plural(1, 'dish', 'dishes')).toBe('1 dish')
  })

  it('pluralises otherwise', () => {
    expect(plural(0, 'dish', 'dishes')).toBe('0 dishes')
    expect(plural(4, 'item')).toBe('4 items')
  })
})
