import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AddressPanel } from '../../../src/pages/account/AddressPanel'

const HOME = {
  id: 7,
  label: 'home',
  line1: '221B Baker Street',
  line2: null,
  city: 'London',
  postal_code: 'NW1',
  is_default: true,
}

const mocks = vi.hoisted(() => ({
  listAddresses: vi.fn(),
  addAddress: vi.fn(),
  updateAddress: vi.fn(),
  deleteAddress: vi.fn(),
}))

vi.mock('../../../src/api/auth', () => ({ authApi: mocks }))

beforeEach(() => {
  mocks.listAddresses.mockReset().mockResolvedValue([HOME])
  mocks.addAddress.mockReset().mockResolvedValue(HOME)
  mocks.updateAddress.mockReset().mockResolvedValue(HOME)
  mocks.deleteAddress.mockReset().mockResolvedValue(undefined)
})

async function openEditor() {
  render(<AddressPanel />)
  await screen.findByText('221B Baker Street', { exact: false })
  await userEvent.click(screen.getByRole('button', { name: 'Edit home' }))
}

describe('AddressPanel editing', () => {
  it('prefills the form with the address being edited', async () => {
    await openEditor()

    expect(screen.getByLabelText('Street Address')).toHaveValue('221B Baker Street')
    const cityInputs = screen.getAllByPlaceholderText(/search city|enter city/i)
    expect(cityInputs[0]).toHaveValue('London')
    expect(screen.getByLabelText('Postal code')).toHaveValue('NW1')
  })

  it('patches only the edited address', async () => {
    await openEditor()

    const cityInputs = screen.getAllByPlaceholderText(/search city|enter city/i)
    const city = cityInputs[0]
    await userEvent.clear(city)
    await userEvent.type(city, 'Manchester')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(mocks.updateAddress).toHaveBeenCalledTimes(1))
    expect(mocks.updateAddress.mock.calls[0][0]).toBe(HOME.id)
    expect(mocks.updateAddress.mock.calls[0][1]).toMatchObject({ city: 'Manchester', label: 'home' })
    expect(mocks.addAddress).not.toHaveBeenCalled()
  })

  it('closes the form and reloads the list after saving', async () => {
    await openEditor()

    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(screen.queryByLabelText('Street Address')).not.toBeInTheDocument())
    expect(mocks.listAddresses).toHaveBeenCalledTimes(2)
  })

  it('discards the edit on cancel', async () => {
    await openEditor()

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByLabelText('Street Address')).not.toBeInTheDocument()
    expect(mocks.updateAddress).not.toHaveBeenCalled()
  })

  it('adds rather than patches when the add form is used', async () => {
    render(<AddressPanel />)
    await screen.findByText('221B Baker Street', { exact: false })

    await userEvent.click(screen.getByRole('button', { name: '+ Add' }))
    await userEvent.type(screen.getByLabelText('Street Address'), '1 New Road')
    const cityInputs = screen.getAllByPlaceholderText(/search city|enter city/i)
    await userEvent.type(cityInputs[0], 'Leeds')
    await userEvent.type(screen.getByLabelText('Postal code'), 'LS1')
    await userEvent.click(screen.getByRole('button', { name: 'Save address' }))

    await waitFor(() => expect(mocks.addAddress).toHaveBeenCalledTimes(1))
    expect(mocks.updateAddress).not.toHaveBeenCalled()
  })

  it('reports a failed save without closing the form', async () => {
    mocks.updateAddress.mockRejectedValue(new Error('boom'))
    await openEditor()

    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(screen.getByText(/could not save address/i)).toBeInTheDocument())
    expect(screen.getByLabelText('Street Address')).toBeInTheDocument()
  })
})
