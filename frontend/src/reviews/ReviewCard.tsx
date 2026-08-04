import { useState } from 'react'

import { errorMessage } from '../api/client'
import { reviewsApi } from '../api/reviews'
import type { Review } from '../api/reviews'
import { Alert, Button } from '../components/ui'
import { RatingStars } from './RatingStars'

interface ReviewCardProps {
  review: Review
  /** True when the signed-in user wrote this review. */
  mine: boolean
  /** True when the signed-in user manages the reviewed restaurant. */
  canReply: boolean
  /** True when the signed-in user may remove it (author or admin). */
  canDelete: boolean
  onChanged: (review: Review) => void
  onDeleted: (reviewId: number) => void
}

const STARS = [1, 2, 3, 4, 5]

/**
 * One review, with the controls the viewer is actually entitled to.
 *
 * The permission booleans are passed in rather than derived here so the card
 * stays presentational and the page owns the one place that reads roles. The
 * server enforces the same rules regardless — these only decide what to render.
 */
export function ReviewCard({
  review, mine, canReply, canDelete, onChanged, onDeleted,
}: ReviewCardProps) {
  const [mode, setMode] = useState<'view' | 'edit' | 'reply'>('view')
  const [rating, setRating] = useState(review.rating)
  const [comment, setComment] = useState(review.comment ?? '')
  const [reply, setReply] = useState(review.owner_reply ?? '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(action: () => Promise<void>, fallback: string) {
    setError(null)
    setBusy(true)
    try {
      await action()
    } catch (e) {
      setError(errorMessage(e, fallback))
    } finally {
      setBusy(false)
    }
  }

  const saveEdit = () =>
    run(async () => {
      // Send the comment as null when cleared, so the API clears it rather than
      // leaving the old text in place.
      onChanged(await reviewsApi.update(review.id, { rating, comment: comment.trim() || null }))
      setMode('view')
    }, 'Could not save your review.')

  const saveReply = () =>
    run(async () => {
      onChanged(await reviewsApi.reply(review.id, reply.trim()))
      setMode('view')
    }, 'Could not post your reply.')

  const remove = () =>
    run(async () => {
      await reviewsApi.remove(review.id)
      onDeleted(review.id)
    }, 'Could not delete this review.')

  return (
    <article className="review-card">
      <div className="review-head">
        <span className="menu-item-name">{review.reviewer_name}</span>
        {mode === 'edit' ? (
          <span className="star-picker" role="group" aria-label="Rating">
            {STARS.map((star) => (
              <button
                key={star}
                type="button"
                className={`star-btn ${star <= rating ? 'star-on' : ''}`}
                aria-label={`${star} star${star > 1 ? 's' : ''}`}
                aria-pressed={star === rating}
                onClick={() => setRating(star)}
              >
                ★
              </button>
            ))}
          </span>
        ) : (
          <RatingStars value={review.rating} />
        )}
        <span className="muted">
          {new Date(review.created_at).toLocaleDateString()}
          {review.updated_at && ' · edited'}
        </span>
      </div>

      {error && <Alert>{error}</Alert>}

      {mode === 'edit' ? (
        <div className="review-editor">
          <textarea
            className="input"
            rows={3}
            aria-label="Your review"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <div className="review-actions">
            <Button variant="ghost" loading={busy} onClick={() => void saveEdit()}>
              Save
            </Button>
            <Button variant="ghost" onClick={() => setMode('view')}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        review.comment && <p className="review-comment">{review.comment}</p>
      )}

      {review.owner_reply && mode !== 'reply' && (
        <p className="review-reply">
          <strong>Response from the restaurant:</strong> {review.owner_reply}
        </p>
      )}

      {mode === 'reply' && (
        <div className="review-editor">
          <textarea
            className="input"
            rows={3}
            aria-label="Your reply"
            value={reply}
            onChange={(e) => setReply(e.target.value)}
          />
          <div className="review-actions">
            <Button variant="ghost" loading={busy} disabled={!reply.trim()} onClick={() => void saveReply()}>
              Post reply
            </Button>
            <Button variant="ghost" onClick={() => setMode('view')}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {mode === 'view' && (mine || canReply || canDelete) && (
        <div className="review-actions">
          {mine && (
            <Button variant="ghost" onClick={() => setMode('edit')}>
              Edit
            </Button>
          )}
          {canReply && (
            <Button variant="ghost" onClick={() => setMode('reply')}>
              {review.owner_reply ? 'Edit reply' : 'Reply'}
            </Button>
          )}
          {canDelete && (
            <Button variant="ghost" loading={busy} onClick={() => void remove()}>
              Delete
            </Button>
          )}
        </div>
      )}
    </article>
  )
}
