import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '../api/client'
import { reviewsApi } from '../api/reviews'
import type { Review } from '../api/reviews'
import { Alert, Button, Loading } from '../components/ui'
import { RatingStars } from './RatingStars'

const PAGE = 5

/**
 * The review list for one restaurant, paged.
 *
 * Owns its own fetching so the surrounding page does not have to thread review
 * state through; the rating summary comes from the restaurant payload instead,
 * which is why this only ever asks for the list.
 */
export function ReviewsSection({ restaurantId }: { restaurantId: number }) {
  const [reviews, setReviews] = useState<Review[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // A short page means the end; a full one means there may be more.
  const [maybeMore, setMaybeMore] = useState(false)

  const loadPage = useCallback(
    async (offset: number) => {
      setBusy(true)
      setError(null)
      try {
        const page = await reviewsApi.forRestaurant(restaurantId, PAGE, offset)
        setReviews((current) => (offset === 0 ? page : [...(current ?? []), ...page]))
        setMaybeMore(page.length === PAGE)
      } catch (e) {
        setError(errorMessage(e, 'Could not load reviews.'))
        setReviews((current) => current ?? [])
      } finally {
        setBusy(false)
      }
    },
    [restaurantId],
  )

  useEffect(() => {
    void loadPage(0)
  }, [loadPage])

  return (
    <section className="menu-section">
      <h2>Reviews</h2>

      {error && <Alert>{error}</Alert>}

      {reviews === null ? (
        <Loading />
      ) : reviews.length === 0 ? (
        !error && <p className="muted">No reviews yet. Order and be the first to leave one.</p>
      ) : (
        <>
          <div className="review-list">
            {reviews.map((review) => (
              <article key={review.id} className="review-card">
                <div className="review-head">
                  <span className="menu-item-name">{review.reviewer_name}</span>
                  <RatingStars value={review.rating} />
                  <span className="muted">{new Date(review.created_at).toLocaleDateString()}</span>
                </div>
                {review.comment && <p className="review-comment">{review.comment}</p>}
              </article>
            ))}
          </div>

          {maybeMore && (
            <Button variant="ghost" loading={busy} onClick={() => void loadPage(reviews.length)}>
              Show more
            </Button>
          )}
        </>
      )}
    </section>
  )
}
