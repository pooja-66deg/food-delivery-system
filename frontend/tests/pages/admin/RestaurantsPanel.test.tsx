import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RestaurantsPanel } from '../../../src/pages/admin/RestaurantsPanel'

const mocks = vi.hoisted(() => ({
  adminList: vi.fn(),
  decideApproval: vi.fn(),
}))

vi.mock('../../../src/api/restaurants', () => ({
  restaurantsApi: { adminList: mocks.adminList, decideApproval: mocks.decideApproval },
  FOOD_TYPE_LABELS: { veg: 'Vegetarian', non_veg: 'Non-vegetarian', both: 'Veg & Non-veg' },
}))

const ROW = {
  id: 7,
  owner_id: 3,
  owner_name: 'Olivia Owner',
  name: 'Tiffin House',
  description: null,
  cuisine: 'Gujarati',
  city: 'Surat',
  address_line: '1 KK Road',
  phone: '+919876500001',
  is_open: false,
  approval_status: 'pending',
  rejection_reason: null,
  food_type: 'veg',
  min_order_amount: 0,
  delivery_radius_km: null,
  image_url: null,
  rating_average: null,
  review_count: 0,
  price_band: null,
  matched_items: [],
}

const page = (items: unknown[]) => ({ items, total: items.length, limit: 100, offset: 0 })

beforeEach(() => {
  mocks.adminList.mockReset().mockResolvedValue(page([ROW]))
  mocks.decideApproval.mockReset().mockResolvedValue({ ...ROW, approval_status: 'approved' })
})

describe('admin restaurant list', () => {
  it('opens on the pending queue, which is where the work is', async () => {
    render(<RestaurantsPanel />)

    await waitFor(() => expect(mocks.adminList).toHaveBeenCalledWith('pending'))
  })

  it('shows every column an operator needs to judge a registration', async () => {
    render(<RestaurantsPanel />)

    expect(await screen.findByText('Tiffin House')).toBeInTheDocument()
    expect(screen.getByText('Olivia Owner')).toBeInTheDocument()
    expect(screen.getByText('Surat')).toBeInTheDocument()
    expect(screen.getByText('1 KK Road')).toBeInTheDocument()
    expect(screen.getByText('+919876500001')).toBeInTheDocument()
    expect(screen.getByText('Vegetarian')).toBeInTheDocument()
    expect(screen.getByText('Closed')).toBeInTheDocument()
    expect(screen.getByText('pending')).toBeInTheDocument()
  })

  it('never offers a way to create a restaurant', async () => {
    // The rule this screen exists to encode: owners register, admins decide.
    render(<RestaurantsPanel />)
    await screen.findByText('Tiffin House')

    expect(screen.queryByRole('button', { name: /add|new|create/i })).not.toBeInTheDocument()
  })

  it('shows an unrated restaurant as unrated, not as nought stars', async () => {
    render(<RestaurantsPanel />)
    await screen.findByText('Tiffin House')

    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('still lists a venue whose owner name has not arrived yet', async () => {
    // The owner read-model is fed by events and can lag. An operator needs to
    // see the venue either way.
    mocks.adminList.mockResolvedValue(page([{ ...ROW, owner_name: '' }]))
    render(<RestaurantsPanel />)

    expect(await screen.findByText('Tiffin House')).toBeInTheDocument()
    expect(screen.getByText('Unknown')).toBeInTheDocument()
  })

  it('approves in one click', async () => {
    render(<RestaurantsPanel />)
    await screen.findByText('Tiffin House')

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() =>
      expect(mocks.decideApproval).toHaveBeenCalledWith(7, 'approved', undefined),
    )
  })

  it('asks for a reason before rejecting, since the owner is shown it', async () => {
    render(<RestaurantsPanel />)
    await screen.findByText('Tiffin House')

    await userEvent.click(screen.getByRole('button', { name: 'Reject' }))
    // Nothing sent yet — the dialog is the point.
    expect(mocks.decideApproval).not.toHaveBeenCalled()

    await userEvent.type(screen.getByRole('textbox'), 'Licence not provided')
    await userEvent.click(screen.getByRole('button', { name: 'Reject restaurant' }))

    await waitFor(() =>
      expect(mocks.decideApproval).toHaveBeenCalledWith(7, 'rejected', 'Licence not provided'),
    )
  })

  it('allows a rejection with no reason given', async () => {
    // Not required: an operator rejecting obvious spam should not have to
    // justify it to the system.
    render(<RestaurantsPanel />)
    await screen.findByText('Tiffin House')

    await userEvent.click(screen.getByRole('button', { name: 'Reject' }))
    await userEvent.click(screen.getByRole('button', { name: 'Reject restaurant' }))

    await waitFor(() =>
      expect(mocks.decideApproval).toHaveBeenCalledWith(7, 'rejected', undefined),
    )
  })

  it('does not offer to approve something already approved', async () => {
    mocks.adminList.mockResolvedValue(page([{ ...ROW, approval_status: 'approved' }]))
    render(<RestaurantsPanel />)
    await screen.findByText('Tiffin House')

    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
  })

  it('shows the rejection reason so an operator can see their own decision', async () => {
    mocks.adminList.mockResolvedValue(
      page([{ ...ROW, approval_status: 'rejected', rejection_reason: 'No licence' }]),
    )
    render(<RestaurantsPanel />)

    expect(await screen.findByText('No licence')).toBeInTheDocument()
  })

  it('refetches when the status filter changes', async () => {
    render(<RestaurantsPanel />)
    await screen.findByText('Tiffin House')

    await userEvent.click(screen.getByRole('button', { name: 'Approved' }))

    await waitFor(() => expect(mocks.adminList).toHaveBeenCalledWith('approved'))
  })

  it('asks for every status on the All tab', async () => {
    render(<RestaurantsPanel />)
    await screen.findByText('Tiffin House')

    await userEvent.click(screen.getByRole('button', { name: 'All' }))

    await waitFor(() => expect(mocks.adminList).toHaveBeenCalledWith(undefined))
  })

  it('says the queue is empty rather than showing a bare table', async () => {
    mocks.adminList.mockResolvedValue(page([]))
    render(<RestaurantsPanel />)

    expect(await screen.findByText(/Nothing waiting for approval/)).toBeInTheDocument()
  })

  it('surfaces a load failure', async () => {
    mocks.adminList.mockRejectedValue(new Error('boom'))
    render(<RestaurantsPanel />)

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
