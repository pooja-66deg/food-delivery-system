import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../../src/api/client'
import { CategoryPanel } from '../../../src/pages/owner/CategoryPanel'

const mocks = vi.hoisted(() => ({
  updateCategory: vi.fn(),
  deleteCategory: vi.fn(),
  addItem: vi.fn(),
  updateItem: vi.fn(),
}))

vi.mock('../../../src/api/restaurants', () => ({ restaurantsApi: mocks }))

const CATEGORY = {
  id: 3,
  name: 'Starters',
  sort_order: 0,
  items: [
    {
      id: 11,
      category_id: 3,
      name: 'Olives',
      description: null,
      price: 4.5,
      is_available: true,
      stock_quantity: null,
      in_stock: true,
      is_vegetarian: false,
      image_url: null,
    },
  ],
}

const noop = () => {}

function renderPanel(overrides: Partial<Parameters<typeof CategoryPanel>[0]> = {}) {
  return render(
    <CategoryPanel
      restaurantId={1}
      category={CATEGORY}
      onChanged={noop}
      onEditItem={noop}
      onSetStock={noop}
      onSetPrice={noop}
      onDeleteItem={noop}
      {...overrides}
    />,
  )
}

beforeEach(() => {
  mocks.updateCategory.mockReset().mockResolvedValue(CATEGORY)
  mocks.deleteCategory.mockReset().mockResolvedValue(undefined)
})

describe('CategoryPanel renaming', () => {
  it('patches the new name and reports the change', async () => {
    const onChanged = vi.fn()
    renderPanel({ onChanged })

    await userEvent.click(screen.getByRole('button', { name: 'Rename Starters' }))
    const input = screen.getByLabelText('Rename Starters')
    await userEvent.clear(input)
    await userEvent.type(input, 'Small plates')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(mocks.updateCategory).toHaveBeenCalledWith(1, 3, { name: 'Small plates' }),
    )
    expect(onChanged).toHaveBeenCalled()
  })

  it('sends nothing when the name is unchanged', async () => {
    renderPanel()

    await userEvent.click(screen.getByRole('button', { name: 'Rename Starters' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(mocks.updateCategory).not.toHaveBeenCalled()
    expect(screen.getByRole('heading', { name: /Starters/ })).toBeInTheDocument()
  })

  it('restores the original name on cancel', async () => {
    renderPanel()

    await userEvent.click(screen.getByRole('button', { name: 'Rename Starters' }))
    await userEvent.type(screen.getByLabelText('Rename Starters'), 'zzz')
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.getByRole('heading', { name: /Starters/ })).toBeInTheDocument()
    expect(mocks.updateCategory).not.toHaveBeenCalled()
  })
})

describe('CategoryPanel deletion', () => {
  it('asks for confirmation before deleting', async () => {
    renderPanel()

    await userEvent.click(screen.getByRole('button', { name: 'Delete category Starters' }))

    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(mocks.deleteCategory).not.toHaveBeenCalled()
  })

  it('deletes once confirmed', async () => {
    const onChanged = vi.fn()
    renderPanel({ onChanged })

    await userEvent.click(screen.getByRole('button', { name: 'Delete category Starters' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(mocks.deleteCategory).toHaveBeenCalledWith(1, 3))
    expect(onChanged).toHaveBeenCalled()
  })

  it('surfaces the API message when the category still holds items', async () => {
    // The 409 explains what to do next; a generic "failed" would not.
    mocks.deleteCategory.mockRejectedValue(
      new ApiError("'Starters' still has 1 item(s). Move or delete them first.", 409),
    )
    renderPanel()

    await userEvent.click(screen.getByRole('button', { name: 'Delete category Starters' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(screen.getByText(/still has 1 item/i)).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: /Starters/ })).toBeInTheDocument()
  })
})
