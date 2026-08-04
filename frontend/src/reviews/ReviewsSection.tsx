import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '../api/client'
import { reviewsApi } from '../api/reviews'
import type { Review } from '../api/reviews'
import { useAuth } from '../auth/AuthContext'
import { Alert, Button, Loading } from '../components/ui'
import { ReviewCard } from './ReviewCard'

const PAGE = 5

/**
 * The review list for one restaurant, paged.
 *
 * Owns its own fetching so the surrounding page does not have to thread review
 * state through; the rating summary comes from the restaurant payload instead,
 * which is why this only ever asks for the list.
 */
export function ReviewsSection({
  restaurantId,
  ownerId,
}: {
  restaurantId: number
  /** Who owns the restaurant, so the reply control shows for them only. */
  ownerId?: number
}) {
  const { user } = useAuth()
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

  // Who the viewer is decides which controls each card offers. The server
  // enforces the same rules; this only avoids showing a button that would 403.
  const isAdmin = user?.role === 'admin'
  const canReply = isAdmin || (user?.role === 'restaurant' && user.id === ownerId)

  const replaceReview = (updated: Review) =>
    setReviews((current) => (current ?? []).map((r) => (r.id === updated.id ? updated : r)))

  const dropReview = (reviewId: number) =>
    setReviews((current) => (current ?? []).filter((r) => r.id !== reviewId))

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
            {reviews.map((review) => {
              const mine = user?.id === review.customer_id
              return (
                <ReviewCard
                  key={review.id}
                  review={review}
                  mine={mine}
                  canReply={canReply}
                  canDelete={mine || isAdmin}
                  onChanged={replaceReview}
                  onDeleted={dropReview}
                />
              )
            })}
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
