import React, { useEffect, useRef, useState, useCallback } from 'react'

interface Prediction {
  place_id: string
  description: string
  main_text?: string
  structured_formatting?: {
    main_text: string
    secondary_text?: string
  }
  types?: string[]
}

interface AutocompleteService {
  getPlacePredictions(request: {
    input: string
    types?: string[]
    componentRestrictions?: { country: string }
  }): Promise<{ predictions: Prediction[] }>
}

interface CityDropdownProps {
  value: string
  onChange: (city: string) => void
  disabled?: boolean
  required?: boolean
}

export const CityDropdown: React.FC<CityDropdownProps> = ({
  value,
  onChange,
  disabled = false,
  required = false,
}) => {
  const [searchInput, setSearchInput] = useState(value)
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [useFallback, setUseFallback] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(-1)

  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const autocompleteRef = useRef<AutocompleteService | null>(null)
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const googleRef = useRef<any>(null)

  useEffect(() => {
    const initializeGooglePlaces = async () => {
      try {
        const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY
        if (!apiKey) {
          console.warn('Google Maps API key not configured - using fallback')
          setUseFallback(true)
          return
        }
        const loadGoogleMaps = (): Promise<void> => {
          return new Promise((resolve, reject) => {
            const win = window as unknown as Record<string, unknown>
            if (win.google) {
              googleRef.current = win.google
              resolve()
              return
            }

            const script = document.createElement('script')
            script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places`
            script.async = true
            script.defer = true
            script.onload = () => {
              const win2 = window as unknown as Record<string, unknown>
              googleRef.current = win2.google
              resolve()
            }
            script.onerror = () => {
              reject(new Error('Failed to load Google Maps API'))
            }
            document.head.appendChild(script)
          })
        }

        await loadGoogleMaps()

        if (googleRef.current) {
          autocompleteRef.current = new (googleRef.current as any).maps.places.AutocompleteService()
        }
      } catch (err) {
        console.error('Failed to initialize Google Places:', err)
        setUseFallback(true)
      }
    }

    initializeGooglePlaces()
  }, [])

  useEffect(() => {
    setSearchInput(value)
  }, [value])

  const handleSearch = useCallback(
    async (inputValue: string) => {
      setSearchInput(inputValue)
      setSelectedIndex(-1)

      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }

      if (!inputValue.trim() || useFallback || !autocompleteRef.current) {
        setPredictions([])
        setIsOpen(false)
        return
      }

      debounceTimerRef.current = setTimeout(async () => {
        try {
          setIsLoading(true)
          setError(null)
          console.log('Fetching city predictions for:', inputValue)
          const result = await autocompleteRef.current!.getPlacePredictions({
            input: inputValue,
            componentRestrictions: { country: 'in' },
          })

          console.log('Raw predictions received:', result.predictions)
          const allPredictions = result.predictions || []

          const seenCities = new Set<string>()
          const cityPredictions: Prediction[] = []

          for (const pred of allPredictions) {
            const mainText = pred.main_text || pred.structured_formatting?.main_text || ''
            if (mainText && !seenCities.has(mainText)) {
              seenCities.add(mainText)
              cityPredictions.push(pred)
            }
          }

          console.log('Unique city predictions:', cityPredictions.length)
          const sliced = cityPredictions.slice(0, 10)
          console.log('Setting predictions to:', sliced)
          setPredictions(sliced)
          console.log('Should open dropdown:', sliced.length > 0)
          setIsOpen(sliced.length > 0)
        } catch (err) {
          console.error('Autocomplete error:', err)
          setError('Failed to load city suggestions')
          setPredictions([])
        } finally {
          setIsLoading(false)
        }
      }, 300)
    },
    [useFallback]
  )

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen || predictions.length === 0) {
      if (e.key === 'Enter' && searchInput.trim()) {
        e.preventDefault()
        onChange(searchInput.trim())
      }
      return
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex((prev) =>
          prev < predictions.length - 1 ? prev + 1 : 0
        )
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex((prev) =>
          prev > 0 ? prev - 1 : predictions.length - 1
        )
        break
      case 'Enter':
        e.preventDefault()
        if (selectedIndex >= 0 && predictions[selectedIndex]) {
          const pred = predictions[selectedIndex]
          const cityName = pred.main_text || pred.structured_formatting?.main_text || ''
          if (cityName) {
            setSearchInput(cityName)
            onChange(cityName)
            setIsOpen(false)
            setPredictions([])
          }
        }
        break
      case 'Escape':
        e.preventDefault()
        setIsOpen(false)
        break
    }
  }

  const handleSelectPrediction = (prediction: Prediction) => {
    console.log('City prediction selected:', prediction)
    const cityName = prediction.main_text || prediction.structured_formatting?.main_text || ''
    console.log('City name extracted:', cityName)
    if (cityName) {
      setSearchInput(cityName)
      onChange(cityName)
      setIsOpen(false)
      setPredictions([])
    }
  }

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  if (useFallback) {
    return (
      <div className="field">
        <label htmlFor="city-input">City</label>
        <input
          id="city-input"
          type="text"
          value={searchInput}
          onChange={(e) => {
            setSearchInput(e.target.value)
            onChange(e.target.value)
          }}
          placeholder="Enter city"
          disabled={disabled}
          required={required}
          className="input"
        />
      </div>
    )
  }

  return (
    <div className="field">
      <label htmlFor="city-dropdown-input">City</label>
      <div className="city-dropdown-container" ref={containerRef}>
        <input
          id="city-dropdown-input"
          ref={inputRef}
          type="text"
          value={searchInput}
          onChange={(e) => handleSearch(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (predictions.length > 0) setIsOpen(true)
          }}
          placeholder="Search city"
          disabled={disabled}
          required={required}
          className="city-dropdown-input input"
          autoComplete="off"
        />

        {isOpen && (
          <div className="city-dropdown-menu">
            {isLoading && <div className="city-dropdown-loading">Loading...</div>}

            {error && <div className="city-dropdown-error">{error}</div>}

            {!isLoading && !error && predictions.length === 0 && searchInput && (
              <div className="city-dropdown-empty">No cities found</div>
            )}

            {!isLoading &&
              !error &&
              predictions.map((prediction, index) => {
                const cityName = prediction.main_text || prediction.structured_formatting?.main_text || ''
                return (
                  <div
                    key={prediction.place_id}
                    className={`city-dropdown-item ${
                      index === selectedIndex ? 'active' : ''
                    }`}
                    onClick={() => handleSelectPrediction(prediction)}
                  >
                    <div className="city-dropdown-main">{cityName}</div>
                    {prediction.structured_formatting?.secondary_text && (
                      <div className="city-dropdown-secondary">
                        {prediction.structured_formatting.secondary_text}
                      </div>
                    )}
                  </div>
                )
              })}
          </div>
        )}
      </div>
    </div>
  )
}
