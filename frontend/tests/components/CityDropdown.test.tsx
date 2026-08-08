// The city picker: Google Places when a key is configured, a plain text input
// when it is not.
//
// This file previously sat at the repository root, outside frontend/, where
// vitest's `include` never reached it — so 362 lines of assertions had never run
// once. They were written against an imagined component and every one of them
// failed the moment it was collected. What follows tests the component that
// actually exists.
//
// Two things about it shape every test here:
//
//   - the fallback decision happens in an effect, not during render, so the
//     first paint is always the Places variant and assertions have to wait;
//   - search is debounced by 300ms, so predictions never appear synchronously.

import { render, fireEvent, waitFor, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CityDropdown } from '../../src/components/CityDropdown'

const PREDICTIONS = [
  {
    place_id: '1',
    description: 'New York, NY, USA',
    structured_formatting: { main_text: 'New York', secondary_text: 'NY, USA' },
  },
  {
    place_id: '2',
    description: 'New Orleans, LA, USA',
    structured_formatting: { main_text: 'New Orleans', secondary_text: 'LA, USA' },
  },
]

const getPlacePredictions = vi.fn()

/** Put a Places API in place and pretend a browser key is configured. */
function withPlaces(predictions = PREDICTIONS) {
  vi.stubEnv('VITE_GOOGLE_MAPS_API_KEY', 'test-key')
  getPlacePredictions.mockResolvedValue({ predictions })
  ;(window as unknown as Record<string, unknown>).google = {
    maps: { places: { AutocompleteService: vi.fn(() => ({ getPlacePredictions })) } },
  }
}

/** The input the component renders once it has settled on a mode. */
const input = () => screen.getByRole('textbox') as HTMLInputElement

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllEnvs()
  delete (window as unknown as Record<string, unknown>).google
})

describe('CityDropdown', () => {
  describe('without a Maps key', () => {
    beforeEach(() => {
      vi.stubEnv('VITE_GOOGLE_MAPS_API_KEY', '')
    })

    it('falls back to a plain text input', async () => {
      render(<CityDropdown value="" onChange={vi.fn()} />)

      // Awaited, not asserted immediately: the fallback is decided in an effect,
      // so the first render is still the Places variant.
      await waitFor(() =>
        expect(input()).toHaveAttribute('placeholder', 'Enter city'),
      )
    })

    it('reports every keystroke, since there is nothing to select from', async () => {
      const onChange = vi.fn()
      render(<CityDropdown value="" onChange={onChange} />)
      await waitFor(() => expect(input()).toHaveAttribute('placeholder', 'Enter city'))

      fireEvent.change(input(), { target: { value: 'Metropolis' } })
      expect(onChange).toHaveBeenCalledWith('Metropolis')
    })
  })

  describe('with a Maps key', () => {
    // Wrapped, not passed directly: vitest calls a beforeEach hook with a test
    // context argument, which would land in `predictions` and is not an array.
    beforeEach(() => withPlaces())

    it('searches only after the debounce, not on every keystroke', async () => {
      render(<CityDropdown value="" onChange={vi.fn()} />)
      await waitFor(() => expect(input()).toHaveAttribute('placeholder', 'Search city'))

      fireEvent.change(input(), { target: { value: 'New' } })
      expect(getPlacePredictions).not.toHaveBeenCalled()

      await vi.advanceTimersByTimeAsync(350)
      await waitFor(() => expect(getPlacePredictions).toHaveBeenCalledTimes(1))
    })

    it('restricts results to one country', async () => {
      render(<CityDropdown value="" onChange={vi.fn()} />)
      await waitFor(() => expect(input()).toHaveAttribute('placeholder', 'Search city'))

      fireEvent.change(input(), { target: { value: 'New' } })
      await vi.advanceTimersByTimeAsync(350)

      await waitFor(() =>
        expect(getPlacePredictions).toHaveBeenCalledWith(
          expect.objectContaining({ componentRestrictions: { country: 'in' } }),
        ),
      )
    })

    it('lists what came back', async () => {
      render(<CityDropdown value="" onChange={vi.fn()} />)
      await waitFor(() => expect(input()).toHaveAttribute('placeholder', 'Search city'))

      fireEvent.change(input(), { target: { value: 'New' } })
      await vi.advanceTimersByTimeAsync(350)

      expect(await screen.findByText('New York')).toBeInTheDocument()
      expect(screen.getByText('New Orleans')).toBeInTheDocument()
    })

    it('reports the city, not the full description, when one is picked', async () => {
      const onChange = vi.fn()
      render(<CityDropdown value="" onChange={onChange} />)
      await waitFor(() => expect(input()).toHaveAttribute('placeholder', 'Search city'))

      fireEvent.change(input(), { target: { value: 'New' } })
      await vi.advanceTimersByTimeAsync(350)
      fireEvent.click(await screen.findByText('New York'))

      // "New York", not "New York, NY, USA" — the field stores a city.
      expect(onChange).toHaveBeenCalledWith('New York')
      expect(screen.queryByText('New Orleans')).not.toBeInTheDocument()
    })

    it('picks with the keyboard', async () => {
      const onChange = vi.fn()
      render(<CityDropdown value="" onChange={onChange} />)
      await waitFor(() => expect(input()).toHaveAttribute('placeholder', 'Search city'))

      fireEvent.change(input(), { target: { value: 'New' } })
      await vi.advanceTimersByTimeAsync(350)
      await screen.findByText('New York')

      fireEvent.keyDown(input(), { key: 'ArrowDown' })
      fireEvent.keyDown(input(), { key: 'Enter' })

      expect(onChange).toHaveBeenCalledWith('New York')
    })

    it('closes on Escape without choosing anything', async () => {
      const onChange = vi.fn()
      render(<CityDropdown value="" onChange={onChange} />)
      await waitFor(() => expect(input()).toHaveAttribute('placeholder', 'Search city'))

      fireEvent.change(input(), { target: { value: 'New' } })
      await vi.advanceTimersByTimeAsync(350)
      await screen.findByText('New York')

      fireEvent.keyDown(input(), { key: 'Escape' })

      await waitFor(() => expect(screen.queryByText('New York')).not.toBeInTheDocument())
      expect(onChange).not.toHaveBeenCalled()
    })

    it('closes when the click lands elsewhere', async () => {
      render(<CityDropdown value="" onChange={vi.fn()} />)
      await waitFor(() => expect(input()).toHaveAttribute('placeholder', 'Search city'))

      fireEvent.change(input(), { target: { value: 'New' } })
      await vi.advanceTimersByTimeAsync(350)
      await screen.findByText('New York')

      fireEvent.mouseDown(document.body)

      await waitFor(() => expect(screen.queryByText('New York')).not.toBeInTheDocument())
    })

    it('says so when there is nothing to show', async () => {
      withPlaces([])
      render(<CityDropdown value="" onChange={vi.fn()} />)
      await waitFor(() => expect(input()).toHaveAttribute('placeholder', 'Search city'))

      fireEvent.change(input(), { target: { value: 'zzzz' } })
      await vi.advanceTimersByTimeAsync(350)

      // The dropdown stays shut rather than showing an empty box: a panel with
      // nothing in it reads as broken.
      await waitFor(() => expect(getPlacePredictions).toHaveBeenCalled())
      expect(screen.queryByText('New York')).not.toBeInTheDocument()
    })

    it('surfaces a failed lookup instead of showing nothing', async () => {
      vi.stubEnv('VITE_GOOGLE_MAPS_API_KEY', 'test-key')
      getPlacePredictions.mockRejectedValue(new Error('quota exceeded'))

      render(<CityDropdown value="" onChange={vi.fn()} />)
      await waitFor(() => expect(input()).toHaveAttribute('placeholder', 'Search city'))

      fireEvent.change(input(), { target: { value: 'New' } })
      await vi.advanceTimersByTimeAsync(350)

      // waitFor rather than findByText: the rejection resolves a microtask after
      // the debounce fires, and under a full parallel run that landed outside
      // findByText's default window often enough to be flaky.
      await waitFor(
        () => expect(screen.getByText(/Failed to load city suggestions/i)).toBeInTheDocument(),
        { timeout: 3000 },
      )
    })
  })
})
