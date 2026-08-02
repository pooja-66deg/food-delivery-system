import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ApiError, errorMessage } from '../../src/api/client'
import { EmptyState, Loading } from '../../src/components/ui'

describe('Loading', () => {
  it('announces itself to screen readers', () => {
    render(<Loading />)

    expect(screen.getByRole('status')).toHaveTextContent('Loading…')
  })

  it('accepts a caller-supplied label', () => {
    render(<Loading label="Fetching orders…" />)

    expect(screen.getByRole('status')).toHaveTextContent('Fetching orders…')
  })

  it('hides the spinner glyph from assistive tech', () => {
    const { container } = render(<Loading />)

    expect(container.querySelector('.spin')).toHaveAttribute('aria-hidden')
  })
})

describe('EmptyState', () => {
  it('renders its message', () => {
    render(<EmptyState>No orders yet.</EmptyState>)

    expect(screen.getByText('No orders yet.')).toBeInTheDocument()
  })

  it('keeps interactive children usable', () => {
    render(
      <EmptyState>
        Nothing here. <a href="/restaurants">Browse</a>
      </EmptyState>,
    )

    expect(screen.getByRole('link', { name: 'Browse' })).toHaveAttribute('href', '/restaurants')
  })
})

describe('errorMessage', () => {
  it('surfaces the message the backend wrote', () => {
    expect(errorMessage(new ApiError('Phone already registered', 409), 'Fallback')).toBe(
      'Phone already registered',
    )
  })

  it('falls back for errors a user could not act on', () => {
    // A TypeError's message is implementation detail — never show it.
    expect(errorMessage(new TypeError('x.y is not a function'), 'Could not load orders.')).toBe(
      'Could not load orders.',
    )
  })

  it('falls back for non-Error throws', () => {
    expect(errorMessage('boom', 'Could not save.')).toBe('Could not save.')
  })

  it('has a generic default when no fallback is given', () => {
    expect(errorMessage(null)).toBe('Something went wrong.')
  })
})
