# Searchable City Dropdown Design

**Date:** 2026-08-06  
**Scope:** Refactor `CityDropdown` component to support real-time city search powered by Google Places API

## Problem Statement

Currently, the `CityDropdown` component is a static `<select>` element that displays a pre-fetched list of cities. Users cannot search or filter the list, making it slow to find cities in large lists. The component has no search capability across any address form in the application.

## Solution Overview

Refactor `CityDropdown` into a searchable input field with a dropdown that fetches city predictions in real-time using Google Places Autocomplete API. The component maintains the same props interface (`value`, `onChange`, `disabled`, `required`) so it's a drop-in replacement everywhere it's currently used.

## User Experience

### Interaction Flow

1. User focuses the input field or starts typing a city name
2. As they type (e.g., "New"), Google Places Autocomplete fetches city predictions
3. A dropdown appears below the input showing matching cities (e.g., "New York", "New Orleans", "Newark")
4. User selects a city by:
   - Clicking on a prediction
   - Using arrow keys to navigate and pressing Enter
   - Typing the full city name and pressing Enter
5. The `onChange` callback fires with the selected city name
6. The dropdown closes and the input retains the selected city

### Keyboard Navigation

- **Arrow Up/Down:** Navigate predictions in dropdown
- **Enter:** Select highlighted prediction
- **Escape:** Close dropdown without selecting
- **Backspace:** Clear selection and allow new search

### Edge Cases

- **No predictions found:** Show "No cities found" message in dropdown
- **API unavailable:** Fall back to plain text input (user can type freely)
- **API error during search:** Show error message, keep dropdown closed, allow user to continue typing
- **Empty input:** Show dropdown on focus (no search needed yet)

## Technical Design

### Component Interface

```typescript
interface CityDropdownProps {
  value: string;           // Currently selected city name
  onChange: (city: string) => void;
  disabled?: boolean;
  required?: boolean;
}
```

**No interface changes** — existing consumers require no modifications.

### State Management

```typescript
- value: string                  // Selected city from props
- searchInput: string            // What user is currently typing
- predictions: Prediction[]      // Array of city suggestions from Google Places
- isOpen: boolean                // Dropdown visibility
- isLoading: boolean             // Fetching predictions from API
- error: string | null           // Error message if API call fails
- selectedIndex: number          // Keyboard navigation position in dropdown
```

### Google Places Integration

**API Used:** `AutocompleteService.getPlacePredictions()`

**Request Parameters:**
- `input`: User's typed city name (e.g., "New")
- `types`: `['(cities)']` — restrict to city/town predictions only
- `componentRestrictions`: None (search globally) or `{ country: 'us' }` if preferred

**Response Extraction:**
- Filter predictions by `types` containing `'locality'` or similar
- Extract city name from prediction's `main_text` or `description` field
- Ignore full address predictions and place names that aren't cities

### Fallback Behavior

If the Google Maps API key is not configured in `VITE_GOOGLE_MAPS_API_KEY`:
- Fall back to a plain text `<input type="text">` 
- User can type any city name freely
- No autocomplete or validation

If API fails during runtime:
- Display error message in the dropdown
- Keep the text input accessible
- User can still type and submit a custom city name

### Debouncing & Performance

- Debounce API calls to 300ms after user stops typing (avoid too many requests per keystroke)
- Cancel in-flight requests when user clears the input or closes dropdown
- Cache predictions for the same search term during the same session to reduce API calls

### Styling

New CSS classes:
- `.city-dropdown-container` — wrapper with relative positioning
- `.city-dropdown-input` — the text input field
- `.city-dropdown-menu` — the dropdown list (positioned absolutely below input)
- `.city-dropdown-item` — individual city prediction
- `.city-dropdown-item.active` — keyboard-selected item (highlighted)
- `.city-dropdown-loading` — loading spinner
- `.city-dropdown-error` — error message
- `.city-dropdown-empty` — "No cities found" message

Styling should match existing form field styles in `index.css`.

## Files to Modify

1. **`frontend/src/components/CityDropdown.tsx`**
   - Refactor from `<select>` to searchable `<input>` with dropdown
   - Add Google Places integration (reuse pattern from `AddressAutocomplete`)
   - Add keyboard navigation logic
   - Keep prop interface unchanged

2. **`frontend/src/index.css`**
   - Add dropdown positioning and styling classes
   - Ensure dark/light theme support
   - Responsive design (dropdown fits on mobile)

## Usage (No Changes Required)

Existing code continues to work without modification:

```typescript
<CityDropdown 
  value={city}
  onChange={setCity}
  required
/>
```

Components already using `CityDropdown`:
- `AddressForm.tsx` — User address form
- `RestaurantForm.tsx` — Restaurant address form
- Any other forms with city fields

All consumers automatically get the searchable experience.

## Testing Strategy

1. **Unit Tests** (`tests/components/CityDropdown.test.tsx`):
   - API key missing → falls back to text input
   - Typing shows predictions
   - Selecting prediction fires onChange with city name
   - Keyboard navigation (arrow keys, Enter, Escape)
   - Debouncing (verify no excessive API calls)
   - Error handling (API fails → shows error, allows fallback)

2. **Integration Tests**:
   - AddressForm with searchable city dropdown
   - RestaurantForm with searchable city dropdown

3. **Manual Testing**:
   - Type a few characters, verify predictions appear
   - Select with mouse and keyboard
   - Test on mobile viewport
   - Test with API key missing
   - Test with API error

## Implementation Order

1. Create new `CityDropdown.tsx` with full search functionality and fallback
2. Update `index.css` with dropdown styling
3. Write unit tests
4. Manual testing in forms (AddressForm, RestaurantForm)
5. Verify no regressions in existing forms

## Success Criteria

- ✅ Users can search cities by typing (no static list)
- ✅ Dropdown shows up to 5-10 city predictions
- ✅ Selecting a city triggers `onChange` with correct value
- ✅ Works on desktop and mobile (dropdown doesn't overflow)
- ✅ Falls back to text input if Google Places API unavailable
- ✅ All existing consumers (AddressForm, RestaurantForm, etc.) work without changes
- ✅ Keyboard navigation (arrows, Enter, Escape) works
- ✅ Unit and integration tests pass
