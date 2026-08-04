import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RatingSummary } from '../../src/reviews/RatingSummary'

const BREAKDOWN = { '5': 2, '4': 0, '3': 1, '2': 0, '1': 0 }
const EMPTY = { '5': 0, '4': 0, '3': 0, '2': 0, '1': 0 }

describe('RatingSummary', () => {
  it('leads with the average and the count', () => {
    render(<RatingSummary average={4.3} count={3} breakdown={BREAKDOWN} />)

    expect(screen.getByText('4.3')).toBeInTheDocument()
    expect(screen.getByText('3 reviews')).toBeInTheDocument()
  })

  it('counts a single review in the singular', () => {
    render(<RatingSummary average={5} count={1} breakdown={{ ...EMPTY, '5': 1 }} />)

    expect(screen.getByText('1 review')).toBeInTheDocument()
  })

  it('shows how many gave each star', () => {
    // A 4.3 from two 5s and a 3 is a different restaurant from a hundred 4s.
    render(<RatingSummary average={4.3} count={3} breakdown={BREAKDOWN} />)

    expect(screen.getByLabelText('5 stars: 2 reviews')).toBeInTheDocument()
    expect(screen.getByLabelText('3 stars: 1 review')).toBeInTheDocument()
    expect(screen.getByLabelText('4 stars: 0 reviews')).toBeInTheDocument()
  })

  it('lists all five rows even when most are empty', () => {
    const { container } = render(<RatingSummary average={5} count={1} breakdown={{ ...EMPTY, '5': 1 }} />)

    expect(container.querySelectorAll('[data-star-row]')).toHaveLength(5)
  })

  it('says so plainly when nothing is rated yet', () => {
    render(<RatingSummary average={null} count={0} breakdown={EMPTY} />)

    expect(screen.getByText(/no reviews yet/i)).toBeInTheDocument()
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })
})
