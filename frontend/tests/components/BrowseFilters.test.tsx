import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BrowseFilters, NO_FACETS } from '../../src/components/BrowseFilters'
import type { Facets } from '../../src/components/BrowseFilters'

const onChange = vi.fn()

function renderFilters(value: Facets = NO_FACETS) {
  return render(<BrowseFilters value={value} onChange={onChange} />)
}

describe('BrowseFilters', () => {
  beforeEach(() => onChange.mockReset())

  it('reports the whole filter set so the page makes one request per change', async () => {
    renderFilters({ sort: 'rating', vegetarian_only: true })

    await userEvent.click(screen.getByRole('button', { name: '4★ & up' }))

    expect(onChange).toHaveBeenCalledWith({
      sort: 'rating',
      vegetarian_only: true,
      min_rating: 4,
    })
  })

  it('re-picking the active chip clears that filter', async () => {
    renderFilters({ ...NO_FACETS, price_band: 2 })

    await userEvent.click(screen.getByRole('button', { name: '₹₹' }))

    expect(onChange).toHaveBeenCalledWith({ sort: 'name', price_band: undefined })
  })

  it('marks the active chips as pressed', () => {
    renderFilters({ ...NO_FACETS, min_rating: 3, vegetarian_only: true })

    expect(screen.getByRole('button', { name: '3★ & up' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Vegetarian' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '4★ & up' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('toggles the dietary filter on and off', async () => {
    renderFilters()
    await userEvent.click(screen.getByRole('button', { name: 'Vegetarian' }))
    expect(onChange).toHaveBeenCalledWith({ sort: 'name', vegetarian_only: true })

    onChange.mockReset()
    renderFilters({ ...NO_FACETS, vegetarian_only: true })
    await userEvent.click(screen.getAllByRole('button', { name: 'Vegetarian' })[1])
    expect(onChange).toHaveBeenCalledWith({ sort: 'name', vegetarian_only: false })
  })

  it('changes the sort', async () => {
    renderFilters()

    await userEvent.selectOptions(screen.getByRole('combobox', { name: /sort/i }), 'price_low')

    expect(onChange).toHaveBeenCalledWith({ sort: 'price_low' })
  })

  it('defaults to sorting by name', () => {
    renderFilters()

    expect(screen.getByRole('combobox', { name: /sort/i })).toHaveValue('name')
  })
})
