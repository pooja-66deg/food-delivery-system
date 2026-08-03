import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ItemForm } from '../../../src/pages/owner/ItemForm'

const mocks = vi.hoisted(() => ({
  addItem: vi.fn(),
  updateItem: vi.fn(),
}))

vi.mock('../../../src/api/restaurants', () => ({ restaurantsApi: mocks }))

const TRACKED_ITEM = {
  id: 11,
  category_id: 3,
  name: 'Olives',
  description: null,
  price: 4.5,
  is_available: true,
  stock_quantity: 7,
  in_stock: true,
  image_url: null,
}

beforeEach(() => {
  mocks.addItem.mockReset().mockResolvedValue(TRACKED_ITEM)
  mocks.updateItem.mockReset().mockResolvedValue(TRACKED_ITEM)
})

describe('ItemForm stock field', () => {
  it('sends null when stock is left blank', async () => {
    // Blank means "sell this without tracking stock", which the API models as null.
    render(<ItemForm restaurantId={1} categoryId={3} onDone={() => {}} />)

    await userEvent.type(screen.getByLabelText('Item name'), 'Bread')
    await userEvent.type(screen.getByLabelText('Item price'), '3.00')
    await userEvent.click(screen.getByRole('button', { name: 'Add item' }))

    await waitFor(() => expect(mocks.addItem).toHaveBeenCalled())
    expect(mocks.addItem.mock.calls[0][1]).toMatchObject({
      category_id: 3,
      name: 'Bread',
      stock_quantity: null,
    })
  })

  it('sends the number that was typed', async () => {
    render(<ItemForm restaurantId={1} categoryId={3} onDone={() => {}} />)

    await userEvent.type(screen.getByLabelText('Item name'), 'Bread')
    await userEvent.type(screen.getByLabelText('Item price'), '3.00')
    await userEvent.type(screen.getByLabelText('Stock quantity'), '12')
    await userEvent.click(screen.getByRole('button', { name: 'Add item' }))

    await waitFor(() => expect(mocks.addItem).toHaveBeenCalled())
    expect(mocks.addItem.mock.calls[0][1].stock_quantity).toBe(12)
  })

  it('prefills the existing count when editing', () => {
    render(
      <ItemForm restaurantId={1} categoryId={3} item={TRACKED_ITEM} onDone={() => {}} />,
    )

    expect(screen.getByLabelText('Stock quantity')).toHaveValue(7)
  })

  it('clearing the count stops tracking stock', async () => {
    render(
      <ItemForm restaurantId={1} categoryId={3} item={TRACKED_ITEM} onDone={() => {}} />,
    )

    await userEvent.clear(screen.getByLabelText('Stock quantity'))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(mocks.updateItem).toHaveBeenCalled())
    expect(mocks.updateItem.mock.calls[0][2].stock_quantity).toBeNull()
  })

  it('sends zero as zero, not as untracked', async () => {
    // Zero is "sold out"; null is "not tracked". They must not collapse.
    render(
      <ItemForm restaurantId={1} categoryId={3} item={TRACKED_ITEM} onDone={() => {}} />,
    )

    const stock = screen.getByLabelText('Stock quantity')
    await userEvent.clear(stock)
    await userEvent.type(stock, '0')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(mocks.updateItem).toHaveBeenCalled())
    expect(mocks.updateItem.mock.calls[0][2].stock_quantity).toBe(0)
  })
})
