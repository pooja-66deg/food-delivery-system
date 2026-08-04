import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { FavoriteButton } from '../../src/components/FavoriteButton'

const mocks = vi.hoisted(() => ({ add: vi.fn(), remove: vi.fn() }))

vi.mock('../../src/api/favorites', () => ({ favoritesApi: mocks }))

const onToggled = vi.fn()

describe('FavoriteButton', () => {
  beforeEach(() => {
    mocks.add.mockReset().mockResolvedValue(undefined)
    mocks.remove.mockReset().mockResolvedValue(undefined)
    onToggled.mockReset()
  })

  it('saves an unsaved restaurant', async () => {
    render(<FavoriteButton restaurantId={7} saved={false} onToggled={onToggled} />)

    await userEvent.click(screen.getByRole('button', { name: /save to favourites/i }))

    await waitFor(() => expect(mocks.add).toHaveBeenCalledWith(7))
    expect(onToggled).toHaveBeenCalledWith(7, true)
  })

  it('removes a saved restaurant', async () => {
    render(<FavoriteButton restaurantId={7} saved onToggled={onToggled} />)

    await userEvent.click(screen.getByRole('button', { name: /remove from favourites/i }))

    await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith(7))
    expect(onToggled).toHaveBeenCalledWith(7, false)
  })

  it('reports the new state before the request resolves', async () => {
    // Optimistic: a heart that waits for a round trip feels broken.
    let release: () => void = () => {}
    mocks.add.mockReturnValue(new Promise<void>((resolve) => (release = resolve)))
    render(<FavoriteButton restaurantId={7} saved={false} onToggled={onToggled} />)

    await userEvent.click(screen.getByRole('button', { name: /save/i }))

    expect(onToggled).toHaveBeenCalledWith(7, true)
    release()
  })

  it('reverts when the request fails', async () => {
    mocks.add.mockRejectedValue(new Error('offline'))
    render(<FavoriteButton restaurantId={7} saved={false} onToggled={onToggled} />)

    await userEvent.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() => expect(onToggled).toHaveBeenLastCalledWith(7, false))
  })

  it('reflects the saved state to assistive tech', () => {
    render(<FavoriteButton restaurantId={7} saved onToggled={onToggled} />)

    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true')
  })
})
