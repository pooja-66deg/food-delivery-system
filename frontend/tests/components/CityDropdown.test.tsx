import React from 'react'
import { render, fireEvent, waitFor } from '@testing-library/react'
import { CityDropdown } from '../../src/components/CityDropdown'

const mockPredictions = [
  { place_id: '1', description: 'New York, NY, USA', main_text: 'New York', types: ['locality'] },
  { place_id: '2', description: 'New Orleans, LA, USA', main_text: 'New Orleans', types: ['locality'] },
  { place_id: '3', description: 'Newark, NJ, USA', main_text: 'Newark', types: ['locality'] },
]

const mockGetPlacePredictions = jest.fn()

beforeEach(() => {
  jest.clearAllMocks()

  // Mock window.google
  ;(window as any).google = {
    maps: {
      places: {
        AutocompleteService: jest.fn(() => ({
          getPlacePredictions: mockGetPlacePredictions,
        })),
      },
    },
  }

  // Default mock to return predictions
  mockGetPlacePredictions.mockResolvedValue({ predictions: mockPredictions })

  // Clear environment variable
  delete (import.meta as any).env.VITE_GOOGLE_MAPS_API_KEY
})

describe('CityDropdown', () => {
  describe('Fallback behavior', () => {
    it('renders text input when API key is missing', () => {
      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} />
      )

      const input = container.querySelector('input[type="text"]')
      expect(input).toBeInTheDocument()
      expect(input).toHaveAttribute('placeholder', 'Enter city')
    })

    it('updates value when typing in fallback mode', async () => {
      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} />
      )

      const input = container.querySelector('input[type="text"]') as HTMLInputElement
      fireEvent.change(input, { target: { value: 'New York' } })

      await waitFor(() => {
        expect(onChange).toHaveBeenCalledWith('New York')
      })
    })
  })

  describe('Search functionality', () => {
    beforeEach(() => {
      ;(import.meta as any).env = { VITE_GOOGLE_MAPS_API_KEY: 'test-key' }
    })

    it('renders searchable input with API key', async () => {
      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} />
      )

      await waitFor(() => {
        const input = container.querySelector('.city-dropdown-input') as HTMLInputElement
        expect(input).toBeInTheDocument()
      })
    })

    it('fetches predictions when user types', async () => {
      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} />
      )

      const input = container.querySelector('.city-dropdown-input') as HTMLInputElement
      fireEvent.change(input, { target: { value: 'New' } })

      await waitFor(
        () => {
          expect(mockGetPlacePredictions).toHaveBeenCalledWith(
            expect.objectContaining({ input: 'New', types: ['(cities)'] })
          )
        },
        { timeout: 500 }
      )
    })

    it('displays predictions in dropdown', async () => {
      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} />
      )

      const input = container.querySelector('.city-dropdown-input') as HTMLInputElement
      fireEvent.change(input, { target: { value: 'New' } })

      await waitFor(() => {
        const items = container.querySelectorAll('.city-dropdown-item')
        expect(items.length).toBe(3)
        expect(items[0].textContent).toBe('New York')
        expect(items[1].textContent).toBe('New Orleans')
        expect(items[2].textContent).toBe('Newark')
      })
    })

    it('shows "No cities found" when search returns no predictions', async () => {
      mockGetPlacePredictions.mockResolvedValueOnce({ predictions: [] })

      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} />
      )

      const input = container.querySelector('.city-dropdown-input') as HTMLInputElement
      fireEvent.change(input, { target: { value: 'XYZ' } })

      await waitFor(() => {
        const empty = container.querySelector('.city-dropdown-empty')
        expect(empty?.textContent).toBe('No cities found')
      })
    })

    it('closes dropdown when clicking outside', async () => {
      const onChange = jest.fn()
      const { container } = render(
        <div>
          <CityDropdown value="" onChange={onChange} />
          <div data-testid="outside">Outside</div>
        </div>
      )

      const input = container.querySelector('.city-dropdown-input') as HTMLInputElement
      fireEvent.change(input, { target: { value: 'New' } })

      await waitFor(() => {
        expect(container.querySelector('.city-dropdown-menu')).toBeInTheDocument()
      })

      fireEvent.mouseDown(container.querySelector('[data-testid="outside"]')!)

      await waitFor(() => {
        expect(container.querySelector('.city-dropdown-menu')).not.toBeInTheDocument()
      })
    })
  })

  describe('Selection', () => {
    beforeEach(() => {
      ;(import.meta as any).env = { VITE_GOOGLE_MAPS_API_KEY: 'test-key' }
    })

    it('calls onChange with city name when prediction is clicked', async () => {
      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} />
      )

      const input = container.querySelector('.city-dropdown-input') as HTMLInputElement
      fireEvent.change(input, { target: { value: 'New' } })

      await waitFor(() => {
        const items = container.querySelectorAll('.city-dropdown-item')
        expect(items.length).toBeGreaterThan(0)
      })

      const firstItem = container.querySelector('.city-dropdown-item') as HTMLDivElement
      fireEvent.click(firstItem)

      expect(onChange).toHaveBeenCalledWith('New York')
    })

    it('closes dropdown after selection', async () => {
      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} />
      )

      const input = container.querySelector('.city-dropdown-input') as HTMLInputElement
      fireEvent.change(input, { target: { value: 'New' } })

      await waitFor(() => {
        expect(container.querySelector('.city-dropdown-menu')).toBeInTheDocument()
      })

      const firstItem = container.querySelector('.city-dropdown-item') as HTMLDivElement
      fireEvent.click(firstItem)

      await waitFor(() => {
        expect(container.querySelector('.city-dropdown-menu')).not.toBeInTheDocument()
      })
    })
  })

  describe('Keyboard navigation', () => {
    beforeEach(() => {
      ;(import.meta as any).env = { VITE_GOOGLE_MAPS_API_KEY: 'test-key' }
    })

    it('navigates predictions with arrow keys', async () => {
      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} />
      )

      const input = container.querySelector('.city-dropdown-input') as HTMLInputElement
      fireEvent.change(input, { target: { value: 'New' } })

      await waitFor(() => {
        const items = container.querySelectorAll('.city-dropdown-item')
        expect(items.length).toBeGreaterThan(0)
      })

      fireEvent.keyDown(input, { key: 'ArrowDown' })

      await waitFor(() => {
        const firstItem = container.querySelector('.city-dropdown-item.active')
        expect(firstItem?.textContent).toBe('New York')
      })

      fireEvent.keyDown(input, { key: 'ArrowDown' })

      await waitFor(() => {
        const items = container.querySelectorAll('.city-dropdown-item.active')
        const active = items[0]
        expect(active?.textContent).toBe('New Orleans')
      })
    })

    it('selects prediction with Enter key', async () => {
      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} />
      )

      const input = container.querySelector('.city-dropdown-input') as HTMLInputElement
      fireEvent.change(input, { target: { value: 'New' } })

      await waitFor(() => {
        const items = container.querySelectorAll('.city-dropdown-item')
        expect(items.length).toBeGreaterThan(0)
      })

      fireEvent.keyDown(input, { key: 'ArrowDown' })

      await waitFor(() => {
        expect(container.querySelector('.city-dropdown-item.active')).toBeInTheDocument()
      })

      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(onChange).toHaveBeenCalledWith('New York')
      })
    })

    it('closes dropdown with Escape key', async () => {
      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} />
      )

      const input = container.querySelector('.city-dropdown-input') as HTMLInputElement
      fireEvent.change(input, { target: { value: 'New' } })

      await waitFor(() => {
        expect(container.querySelector('.city-dropdown-menu')).toBeInTheDocument()
      })

      fireEvent.keyDown(input, { key: 'Escape' })

      await waitFor(() => {
        expect(container.querySelector('.city-dropdown-menu')).not.toBeInTheDocument()
      })
    })

    it('selects from fallback input with Enter key', async () => {
      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} />
      )

      const input = container.querySelector('input[type="text"]') as HTMLInputElement
      fireEvent.change(input, { target: { value: 'Custom City' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      expect(onChange).toHaveBeenCalledWith('Custom City')
    })
  })

  describe('Error handling', () => {
    beforeEach(() => {
      ;(import.meta as any).env = { VITE_GOOGLE_MAPS_API_KEY: 'test-key' }
    })

    it('shows error message when API call fails', async () => {
      mockGetPlacePredictions.mockRejectedValueOnce(new Error('API Error'))

      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} />
      )

      const input = container.querySelector('.city-dropdown-input') as HTMLInputElement
      fireEvent.change(input, { target: { value: 'New' } })

      await waitFor(() => {
        const error = container.querySelector('.city-dropdown-error')
        expect(error?.textContent).toContain('Failed to load city suggestions')
      })
    })
  })

  describe('Props', () => {
    beforeEach(() => {
      ;(import.meta as any).env = { VITE_GOOGLE_MAPS_API_KEY: 'test-key' }
    })

    it('respects disabled prop', () => {
      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} disabled />
      )

      const input = container.querySelector('.city-dropdown-input') as HTMLInputElement
      expect(input.disabled).toBe(true)
    })

    it('respects required prop', () => {
      const onChange = jest.fn()
      const { container } = render(
        <CityDropdown value="" onChange={onChange} required />
      )

      const input = container.querySelector('.city-dropdown-input') as HTMLInputElement
      expect(input.required).toBe(true)
    })

    it('syncs value prop changes to input', async () => {
      const onChange = jest.fn()
      const { rerender, container } = render(
        <CityDropdown value="" onChange={onChange} />
      )

      rerender(<CityDropdown value="New York" onChange={onChange} />)

      await waitFor(() => {
        const input = container.querySelector('.city-dropdown-input') as HTMLInputElement
        expect(input.value).toBe('New York')
      })
    })
  })
})
