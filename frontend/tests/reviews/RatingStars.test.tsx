import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RatingStars } from '../../src/reviews/RatingStars'

describe('RatingStars', () => {
  it('states the value out of five for screen readers', () => {
    render(<RatingStars value={4.3} />)

    expect(screen.getByRole('img', { name: '4.3 out of 5' })).toBeInTheDocument()
  })

  it('fills the nearest whole star', () => {
    const { container } = render(<RatingStars value={4.3} />)

    expect(container.querySelectorAll('[data-filled="true"]')).toHaveLength(4)
    expect(container.querySelectorAll('[data-filled="false"]')).toHaveLength(1)
  })

  it('rounds a high fraction up', () => {
    const { container } = render(<RatingStars value={4.6} />)

    expect(container.querySelectorAll('[data-filled="true"]')).toHaveLength(5)
  })

  it('always draws five stars', () => {
    const { container } = render(<RatingStars value={1} />)

    expect(container.querySelectorAll('[data-star]')).toHaveLength(5)
  })

  it('renders nothing for an unrated restaurant', () => {
    // Drawing zero stars would read as a one-star rating, not "no rating".
    const { container } = render(<RatingStars value={null} />)

    expect(container).toBeEmptyDOMElement()
  })
})
