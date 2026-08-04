import { RatingStars } from './RatingStars'

const STARS = [5, 4, 3, 2, 1]

export function reviewCountLabel(count: number): string {
  return count === 1 ? '1 review' : `${count} reviews`
}

interface RatingSummaryProps {
  average: number | null
  count: number
  /** Star -> number of reviews. JSON object keys arrive as strings. */
  breakdown: Record<string, number>
}

/**
 * The average, the count, and how the ratings are spread.
 *
 * The spread is the point: a 4.3 from two 5s and a 3 is a different restaurant
 * from a hundred consistent 4s, and an average alone cannot tell them apart.
 */
export function RatingSummary({ average, count, breakdown }: RatingSummaryProps) {
  if (count === 0 || average === null) {
    return <p className="muted">No reviews yet.</p>
  }

  return (
    <div className="rating-summary">
      <div className="rating-headline">
        <span className="rating-average">{average}</span>
        <RatingStars value={average} />
        <span className="muted">{reviewCountLabel(count)}</span>
      </div>

      <div className="rating-bars">
        {STARS.map((star) => {
          const forStar = breakdown[String(star)] ?? 0
          const share = count === 0 ? 0 : Math.round((forStar / count) * 100)
          return (
            <div
              key={star}
              className="rating-bar-row"
              data-star-row={star}
              aria-label={`${star} stars: ${reviewCountLabel(forStar)}`}
            >
              <span className="rating-bar-label">{star}★</span>
              <span className="rating-bar-track">
                <span className="rating-bar-fill" style={{ width: `${share}%` }} />
              </span>
              <span className="rating-bar-count muted">{forStar}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
