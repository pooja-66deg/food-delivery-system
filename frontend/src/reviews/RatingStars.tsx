const STARS = [1, 2, 3, 4, 5]

/**
 * Five stars, filled to the nearest whole one.
 *
 * Purely presentational — it takes a number so it can be rendered anywhere
 * without knowing where the rating came from. An unrated restaurant renders
 * nothing at all: five empty stars would read as a one-star rating rather than
 * as "not rated yet".
 */
export function RatingStars({ value }: { value: number | null }) {
  if (value === null || value === undefined) return null

  const filled = Math.round(value)
  console.log('RatingStars', { value, filled })

  return (
    <span className="rating-stars" role="img" aria-label={`${value} out of 5`}>
      {STARS.map((star) => (
        <span key={star} data-star={star} data-filled={star <= filled} aria-hidden>
          ★
        </span>
      ))}
    </span>
  )
}
