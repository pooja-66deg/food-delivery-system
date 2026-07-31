import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { PopularCuisines } from '../../src/components/PopularCuisines'

const CUISINES = [
  { cuisine: 'Italian', count: 3 },
  { cuisine: 'Japanese', count: 2 },
  { cuisine: 'Thai', count: 1 },
]

describe('PopularCuisines', () => {
  it('renders a button per cuisine', () => {
    render(<PopularCuisines cuisines={CUISINES} onPick={vi.fn()} />)

    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual([
      'Italian',
      'Japanese',
      'Thai',
    ])
  })

  it('reports the chosen cuisine', async () => {
    const onPick = vi.fn()
    render(<PopularCuisines cuisines={CUISINES} onPick={onPick} />)

    await userEvent.click(screen.getByRole('button', { name: 'Japanese' }))

    expect(onPick).toHaveBeenCalledWith('Japanese')
  })

  it('renders nothing when there are no cuisines', () => {
    const { container } = render(<PopularCuisines cuisines={[]} onPick={vi.fn()} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('exposes the restaurant count to assistive tech without cluttering the label', () => {
    render(<PopularCuisines cuisines={CUISINES} onPick={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Italian' })).toHaveAttribute(
      'title',
      '3 restaurants',
    )
  })

  it('uses the singular form for a single restaurant', () => {
    render(<PopularCuisines cuisines={[{ cuisine: 'Thai', count: 1 }]} onPick={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Thai' })).toHaveAttribute('title', '1 restaurant')
  })

  it('is introduced by a label so the chips are not bare', () => {
    render(<PopularCuisines cuisines={CUISINES} onPick={vi.fn()} />)

    expect(screen.getByText(/popular/i)).toBeInTheDocument()
  })
})
