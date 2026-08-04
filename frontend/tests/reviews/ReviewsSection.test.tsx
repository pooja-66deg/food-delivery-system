import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ReviewsSection } from '../../src/reviews/ReviewsSection'

const mocks = vi.hoisted(() => ({ forRestaurant: vi.fn() }))

vi.mock('../../src/api/reviews', () => ({ reviewsApi: mocks }))

function review(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    order_id: 1,
    customer_id: 1,
    restaurant_id: 1,
    rating: 5,
    comment: 'Excellent pizza',
    reviewer_name: 'Alex R.',
    created_at: '2026-08-01T10:00:00Z',
    ...overrides,
  }
}

/** A full page, so the component knows there may be more. */
function fullPage(startId: number) {
  return Array.from({ length: 5 }, (_, i) => review({ id: startId + i }))
}

beforeEach(() => {
  mocks.forRestaurant.mockReset().mockResolvedValue([review()])
})

describe('ReviewsSection', () => {
  it('shows the reviewer, the rating, and the comment', async () => {
    render(<ReviewsSection restaurantId={1} />)

    expect(await screen.findByText('Alex R.')).toBeInTheDocument()
    expect(screen.getByText('Excellent pizza')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '5 out of 5' })).toBeInTheDocument()
  })

  it('renders a rating left without a comment', async () => {
    mocks.forRestaurant.mockResolvedValue([review({ comment: null })])
    render(<ReviewsSection restaurantId={1} />)

    expect(await screen.findByText('Alex R.')).toBeInTheDocument()
  })

  it('invites the first review when there are none', async () => {
    mocks.forRestaurant.mockResolvedValue([])
    render(<ReviewsSection restaurantId={1} />)

    expect(await screen.findByText(/no reviews yet/i)).toBeInTheDocument()
  })

  it('offers Show more only when the page came back full', async () => {
    mocks.forRestaurant.mockResolvedValue(fullPage(1))
    render(<ReviewsSection restaurantId={1} />)

    await screen.findAllByText('Alex R.')
    expect(screen.getByRole('button', { name: /show more/i })).toBeInTheDocument()
  })

  it('hides Show more on a short page', async () => {
    render(<ReviewsSection restaurantId={1} />)

    await screen.findByText('Alex R.')
    expect(screen.queryByRole('button', { name: /show more/i })).not.toBeInTheDocument()
  })

  it('appends the next page rather than replacing it', async () => {
    mocks.forRestaurant.mockResolvedValueOnce(fullPage(1)).mockResolvedValueOnce([review({ id: 99 })])
    render(<ReviewsSection restaurantId={1} />)
    await screen.findAllByText('Alex R.')

    await userEvent.click(screen.getByRole('button', { name: /show more/i }))

    await waitFor(() => expect(screen.getAllByText('Alex R.')).toHaveLength(6))
    expect(mocks.forRestaurant).toHaveBeenLastCalledWith(1, 5, 5)
  })

  it('reports a failure to load', async () => {
    mocks.forRestaurant.mockRejectedValue(new Error('offline'))
    render(<ReviewsSection restaurantId={1} />)

    expect(await screen.findByText(/could not load reviews/i)).toBeInTheDocument()
  })
})
