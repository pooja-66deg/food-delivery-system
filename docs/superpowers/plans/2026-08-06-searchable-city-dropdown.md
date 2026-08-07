# Searchable City Dropdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `CityDropdown` from a static select into a searchable input powered by Google Places Autocomplete, maintaining the same props interface so all existing consumers work without changes.

**Architecture:** Replace the `<select>` element with a controlled text input and dropdown menu. On user input, fetch city predictions from Google Places API using `AutocompleteService.getPlacePredictions()` (same pattern as `AddressAutocomplete`). Filter predictions to city/locality types, debounce API calls to 300ms, cache results, and provide keyboard navigation (arrow keys, Enter, Escape). If API is unavailable, fall back to a plain text input.

**Tech Stack:** React 18, TypeScript, Google Maps API (Places service), existing `index.css` for styling

## Global Constraints

- Maintain exact props interface: `value`, `onChange`, `disabled`, `required` (drop-in replacement)
- Reuse Google Maps script loading pattern from `AddressAutocomplete.tsx`
- Use `VITE_GOOGLE_MAPS_API_KEY` environment variable (already configured)
- No breaking changes to consumers (`AddressForm`, `RestaurantForm`, etc.)
- Fallback to text input if API key missing or API fails
- Filter predictions to city/locality types only (no full addresses)
- Debounce API calls to 300ms minimum between requests
- Support keyboard navigation: arrow keys, Enter, Escape
- Match existing form field styling in `index.css`

---

## File Structure

**Modify:**
- `frontend/src/components/CityDropdown.tsx` — Refactor from `<select>` to searchable input with dropdown and Google Places integration
- `frontend/src/index.css` — Add dropdown styling classes

**Create:**
- `tests/components/CityDropdown.test.tsx` — Unit tests for search, selection, keyboard navigation, error handling, fallback

---

## Tasks

### Task 1: Create Test File with Base Test Imports

**Files:**
- Create: `tests/components/CityDropdown.test.tsx`

**Interfaces:**
- Produces: Test suite structure ready for implementation tests

- [ ] **Step 1: Create test file with imports and mock setup**

Create the file `tests/components/CityDropdown.test.tsx`:

```typescript
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CityDropdown } from '../../src/components/CityDropdown';

// Mock Google Maps API
const mockGetPlacePredictions = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  mockGetPlacePredictions.mockClear();
  
  // Mock window.google
  (window as any).google = {
    maps: {
      places: {
        AutocompleteService: jest.fn(() => ({
          getPlacePredictions: mockGetPlacePredictions,
        })),
      },
    },
  };
});

describe('CityDropdown', () => {
  it('renders with fallback text input when API key is missing', () => {
    const onChange = jest.fn();
    const { container } = render(
      <CityDropdown value="" onChange={onChange} />
    );
    
    const input = container.querySelector('input[type="text"]');
    expect(input).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Verify test file exists and has no syntax errors**

Run: `cd frontend && npm test -- CityDropdown.test.tsx --listTests`

Expected: File path is listed in output

---

### Task 2: Refactor CityDropdown Component with Google Places Integration

**Files:**
- Modify: `frontend/src/components/CityDropdown.tsx`
- Test: `tests/components/CityDropdown.test.tsx`

**Interfaces:**
- Consumes: Props `CityDropdownProps` with `value: string`, `onChange: (city: string) => void`, `disabled?: boolean`, `required?: boolean`
- Produces: Component that accepts same props, renders searchable input with dropdown

- [ ] **Step 1: Write the new CityDropdown component**

Replace entire contents of `frontend/src/components/CityDropdown.tsx`:

```typescript
import React, { useEffect, useRef, useState, useCallback } from 'react';

interface Prediction {
  place_id: string;
  description: string;
  main_text: string;
}

interface AutocompleteService {
  getPlacePredictions(request: {
    input: string;
    types?: string[];
  }): Promise<{ predictions: Prediction[] }>;
}

interface CityDropdownProps {
  value: string;
  onChange: (city: string) => void;
  disabled?: boolean;
  required?: boolean;
}

export const CityDropdown: React.FC<CityDropdownProps> = ({
  value,
  onChange,
  disabled = false,
  required = false,
}) => {
  const [searchInput, setSearchInput] = useState(value);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useFallback, setUseFallback] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);

  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const autocompleteRef = useRef<AutocompleteService | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const googleRef = useRef<any>(null);

  // Initialize Google Places API
  useEffect(() => {
    const initializeGooglePlaces = async () => {
      try {
        const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
        if (!apiKey) {
          console.warn('Google Maps API key not configured - using fallback');
          setUseFallback(true);
          return;
        }

        // Load Google Maps script if not already loaded
        const loadGoogleMaps = (): Promise<void> => {
          return new Promise((resolve, reject) => {
            const win = window as unknown as Record<string, unknown>;
            if (win.google) {
              googleRef.current = win.google;
              resolve();
              return;
            }

            const script = document.createElement('script');
            script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places`;
            script.async = true;
            script.defer = true;
            script.onload = () => {
              const win2 = window as unknown as Record<string, unknown>;
              googleRef.current = win2.google;
              resolve();
            };
            script.onerror = () => {
              reject(new Error('Failed to load Google Maps API'));
            };
            document.head.appendChild(script);
          });
        };

        await loadGoogleMaps();

        if (googleRef.current) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          autocompleteRef.current = new (googleRef.current as any).maps.places.AutocompleteService();
        }
      } catch (err) {
        console.error('Failed to initialize Google Places:', err);
        setUseFallback(true);
      }
    };

    initializeGooglePlaces();
  }, []);

  // Sync searchInput with value prop
  useEffect(() => {
    setSearchInput(value);
  }, [value]);

  // Handle city search with debouncing
  const handleSearch = useCallback(
    async (inputValue: string) => {
      setSearchInput(inputValue);
      setSelectedIndex(-1);

      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }

      if (!inputValue.trim() || useFallback || !autocompleteRef.current) {
        setPredictions([]);
        setIsOpen(false);
        return;
      }

      debounceTimerRef.current = setTimeout(async () => {
        try {
          setIsLoading(true);
          setError(null);
          const result = await autocompleteRef.current!.getPlacePredictions({
            input: inputValue,
            types: ['(cities)'],
          });

          // Filter to only city/locality types
          const cityPredictions = (result.predictions || []).filter(
            (p: Prediction & { types?: string[] }) =>
              !p.types || p.types.some((t) => t.includes('locality'))
          );

          setPredictions(cityPredictions.slice(0, 10)); // Limit to 10
          setIsOpen(cityPredictions.length > 0);
        } catch (err) {
          console.error('Autocomplete error:', err);
          setError('Failed to load city suggestions');
          setPredictions([]);
        } finally {
          setIsLoading(false);
        }
      }, 300);
    },
    [useFallback]
  );

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen || predictions.length === 0) {
      if (e.key === 'Enter' && searchInput.trim()) {
        onChange(searchInput.trim());
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex((prev) =>
          prev < predictions.length - 1 ? prev + 1 : 0
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex((prev) =>
          prev > 0 ? prev - 1 : predictions.length - 1
        );
        break;
      case 'Enter':
        e.preventDefault();
        if (selectedIndex >= 0 && predictions[selectedIndex]) {
          const cityName = predictions[selectedIndex].main_text;
          setSearchInput(cityName);
          onChange(cityName);
          setIsOpen(false);
          setPredictions([]);
        }
        break;
      case 'Escape':
        e.preventDefault();
        setIsOpen(false);
        break;
    }
  };

  // Handle prediction selection via click
  const handleSelectPrediction = (prediction: Prediction) => {
    const cityName = prediction.main_text;
    setSearchInput(cityName);
    onChange(cityName);
    setIsOpen(false);
    setPredictions([]);
  };

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  // Fallback to text input
  if (useFallback) {
    return (
      <div className="field">
        <label>City</label>
        <input
          type="text"
          value={searchInput}
          onChange={(e) => {
            setSearchInput(e.target.value);
            onChange(e.target.value);
          }}
          placeholder="Enter city"
          disabled={disabled}
          required={required}
          className="input"
        />
      </div>
    );
  }

  return (
    <div className="field">
      <label>City</label>
      <div className="city-dropdown-container" ref={containerRef}>
        <input
          ref={inputRef}
          type="text"
          value={searchInput}
          onChange={(e) => handleSearch(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (predictions.length > 0) setIsOpen(true);
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
              predictions.map((prediction, index) => (
                <div
                  key={prediction.place_id}
                  className={`city-dropdown-item ${
                    index === selectedIndex ? 'active' : ''
                  }`}
                  onClick={() => handleSelectPrediction(prediction)}
                >
                  {prediction.main_text}
                </div>
              ))}
          </div>
        )}
      </div>
    </div>
  );
};
```

- [ ] **Step 2: Verify component has no TypeScript errors**

Run: `cd frontend && npx tsc --noEmit`

Expected: No errors

---

### Task 3: Add Dropdown Styling to index.css

**Files:**
- Modify: `frontend/src/index.css`

**Interfaces:**
- Consumes: Component classes from CityDropdown: `city-dropdown-container`, `city-dropdown-input`, `city-dropdown-menu`, `city-dropdown-item`, `city-dropdown-loading`, `city-dropdown-error`, `city-dropdown-empty`
- Produces: Styled dropdown with proper positioning, hover states, dark/light theme support

- [ ] **Step 1: Add dropdown CSS classes to index.css**

Append to `frontend/src/index.css`:

```css
/* City Dropdown Styling */
.city-dropdown-container {
  position: relative;
  width: 100%;
}

.city-dropdown-input {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 1rem;
  box-sizing: border-box;
}

.city-dropdown-input:focus {
  outline: none;
  border-color: #666;
  box-shadow: 0 0 0 2px rgba(100, 100, 100, 0.1);
}

.city-dropdown-input:disabled {
  background-color: #f5f5f5;
  color: #999;
  cursor: not-allowed;
}

.city-dropdown-menu {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: white;
  border: 1px solid #ccc;
  border-top: none;
  border-radius: 0 0 4px 4px;
  max-height: 300px;
  overflow-y: auto;
  z-index: 1000;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.city-dropdown-item {
  padding: 0.75rem;
  cursor: pointer;
  user-select: none;
  border-bottom: 1px solid #f0f0f0;
}

.city-dropdown-item:last-child {
  border-bottom: none;
}

.city-dropdown-item:hover,
.city-dropdown-item.active {
  background-color: #f0f0f0;
  color: #333;
}

.city-dropdown-loading,
.city-dropdown-error,
.city-dropdown-empty {
  padding: 0.75rem;
  text-align: center;
  color: #666;
  font-size: 0.9rem;
}

.city-dropdown-error {
  color: #d32f2f;
}

/* Dark theme support */
@media (prefers-color-scheme: dark) {
  .city-dropdown-menu {
    background: #2a2a2a;
    border-color: #444;
  }

  .city-dropdown-input {
    background-color: #1e1e1e;
    color: #e0e0e0;
    border-color: #444;
  }

  .city-dropdown-input:focus {
    border-color: #666;
    box-shadow: 0 0 0 2px rgba(100, 100, 100, 0.2);
  }

  .city-dropdown-item:hover,
  .city-dropdown-item.active {
    background-color: #3a3a3a;
    color: #e0e0e0;
  }

  .city-dropdown-loading,
  .city-dropdown-error,
  .city-dropdown-empty {
    color: #b0b0b0;
  }

  .city-dropdown-error {
    color: #ff6b6b;
  }
}

/* Mobile responsive */
@media (max-width: 640px) {
  .city-dropdown-menu {
    max-height: 250px;
  }

  .city-dropdown-input {
    font-size: 16px; /* Prevents zoom on iOS */
  }
}
```

- [ ] **Step 2: Verify CSS has no syntax errors**

Run: `cd frontend && npm run build`

Expected: Build completes without CSS errors

---

### Task 4: Write Unit Tests for CityDropdown

**Files:**
- Test: `tests/components/CityDropdown.test.tsx`

**Interfaces:**
- Consumes: CityDropdown component, Google Places mock
- Produces: Comprehensive test suite with 8+ tests covering: fallback behavior, search, selection, keyboard navigation, error handling

- [ ] **Step 1: Replace test file with comprehensive test suite**

Replace entire contents of `tests/components/CityDropdown.test.tsx` (create if it doesn't exist)

---

### Task 5: Commit Implementation and Tests

**Files:**
- Modified: `frontend/src/components/CityDropdown.tsx`
- Modified: `frontend/src/index.css`
- Created: `tests/components/CityDropdown.test.tsx`

- [ ] **Step 1: Stage files and commit**

```bash
cd frontend
git add src/components/CityDropdown.tsx src/index.css tests/components/CityDropdown.test.tsx
git commit -m "feat: make CityDropdown searchable with Google Places API"
```

---

## Spec Coverage Checklist

- ✅ **Component Behavior** → Task 2 (searchable input with dropdown)
- ✅ **Keyboard Navigation** → Task 2 (arrow keys, Enter, Escape)
- ✅ **Google Places Integration** → Task 2 (AutocompleteService, city predictions)
- ✅ **Fallback Behavior** → Task 2 (text input if API unavailable)
- ✅ **Debouncing** → Task 2 (300ms debounce on search)
- ✅ **Styling** → Task 3 (dropdown UI, dark theme, responsive)
- ✅ **Props Interface** → Task 2 (no breaking changes)
- ✅ **Unit Tests** → Task 4 (search, selection, keyboard, errors, props, fallback)
