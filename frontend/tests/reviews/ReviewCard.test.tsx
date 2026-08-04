import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../src/api/client'
import type { Review } from '../../src/api/reviews'
import { ReviewCard } from '../../src/reviews/ReviewCard'

const mocks = vi.hoisted(() => ({ update: vi.fn(), remove: vi.fn(), reply: vi.fn() }))

vi.mock('../../src/api/reviews', () => ({ reviewsApi: mocks }))

const REVIEW: Review = {
  id: 5,
  order_id: 12,
  customer_id: 3,
  restaurant_id: 9,
  rating: 3,
  comment: 'It was fine.',
  created_at: '2026-08-01T12:00:00Z',
  updated_at: null,
  owner_reply: null,
  owner_replied_at: null,
  reviewer_name: 'Alex R.',
}

const onChanged = vi.fn()
const onDeleted = vi.fn()

function renderCard(overrides: Record<string, unknown> = {}, review: Review = REVIEW) {
  return render(
    <ReviewCard
      review={review}
      mine={false}
      canReply={false}
      canDelete={false}
      onChanged={onChanged}
      onDeleted={onDeleted}
      {...overrides}
    />,
  )
}

describe('ReviewCard', () => {
  beforeEach(() => {
    mocks.update.mockReset().mockResolvedValue({ ...REVIEW, rating: 5 })
    mocks.remove.mockReset().mockResolvedValue(undefined)
    mocks.reply.mockReset().mockResolvedValue({ ...REVIEW, owner_reply: 'Thanks' })
    onChanged.mockReset()
    onDeleted.mockReset()
  })

  it('offers no controls to a passing reader', () => {
    renderCard()

    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reply' })).not.toBeInTheDocument()
  })

  it('lets the author edit and reports the updated review', async () => {
    renderCard({ mine: true })

    await userEvent.click(screen.getByRole('button', { name: 'Edit' }))
    await userEvent.click(screen.getByRole('button', { name: '5 stars' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(mocks.update).toHaveBeenCalledWith(5, { rating: 5, comment: 'It was fine.' }),
    )
    expect(onChanged).toHaveBeenCalled()
  })

  it('clearing the comment sends null so the API clears it', async () => {
    renderCard({ mine: true })

    await userEvent.click(screen.getByRole('button', { name: 'Edit' }))
    await userEvent.clear(screen.getByLabelText('Your review'))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(mocks.update).toHaveBeenCalledWith(5, { rating: 3, comment: null }),
    )
  })

  it('cancelling an edit leaves the review alone', async () => {
    renderCard({ mine: true })

    await userEvent.click(screen.getByRole('button', { name: 'Edit' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(mocks.update).not.toHaveBeenCalled()
    expect(screen.getByText('It was fine.')).toBeInTheDocument()
  })

  it('marks an edited review as edited', () => {
    renderCard({}, { ...REVIEW, updated_at: '2026-08-02T09:00:00Z' })

    expect(screen.getByText(/edited/)).toBeInTheDocument()
  })

  it('does not mark a fresh review as edited', () => {
    renderCard()

    expect(screen.queryByText(/edited/)).not.toBeInTheDocument()
  })

  it('deletes and reports the removal', async () => {
    renderCard({ mine: true, canDelete: true })

    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith(5))
    expect(onDeleted).toHaveBeenCalledWith(5)
  })

  it('lets the owner reply', async () => {
    renderCard({ canReply: true })

    await userEvent.click(screen.getByRole('button', { name: 'Reply' }))
    await userEvent.type(screen.getByLabelText('Your reply'), 'Sorry about that')
    await userEvent.click(screen.getByRole('button', { name: 'Post reply' }))

    await waitFor(() => expect(mocks.reply).toHaveBeenCalledWith(5, 'Sorry about that'))
  })

  it('will not post an empty reply', async () => {
    renderCard({ canReply: true })

    await userEvent.click(screen.getByRole('button', { name: 'Reply' }))

    expect(screen.getByRole('button', { name: 'Post reply' })).toBeDisabled()
  })

  it('shows an existing reply and offers to edit it', () => {
    renderCard({ canReply: true }, { ...REVIEW, owner_reply: 'We fixed the oven' })

    expect(screen.getByText(/We fixed the oven/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit reply' })).toBeInTheDocument()
  })

  it('surfaces a failure and stays in edit mode', async () => {
    mocks.update.mockRejectedValue(new ApiError('Only the author can edit it', 403))
    renderCard({ mine: true })

    await userEvent.click(screen.getByRole('button', { name: 'Edit' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Only the author can edit it')).toBeInTheDocument()
    expect(screen.getByLabelText('Your review')).toBeInTheDocument()
  })
})
