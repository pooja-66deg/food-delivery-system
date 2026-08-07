import type { BrowseParams, RestaurantSort } from '../api/restaurants'

export type Facets = Pick<
  BrowseParams,
  'min_rating' | 'price_band' | 'vegetarian_only' | 'open_only' | 'sort'
>

export const NO_FACETS: Facets = { sort: 'name' }

const SORTS: { value: RestaurantSort; label: string }[] = [
  { value: 'name', label: 'Name (A–Z)' },
  { value: 'rating', label: 'Top rated' },
  { value: 'price_low', label: 'Price: low to high' },
  { value: 'price_high', label: 'Price: high to low' },
]

const RATINGS = [4, 3]
const BANDS = [
  { value: 1, label: '₹' },
  { value: 2, label: '₹₹' },
  { value: 3, label: '₹₹₹' },
]

interface BrowseFiltersProps {
  value: Facets
  onChange: (next: Facets) => void
}

export function BrowseFilters({ value, onChange }: BrowseFiltersProps) {
  const set = (patch: Partial<Facets>) => onChange({ ...value, ...patch })

  const pick = <K extends keyof Facets>(key: K, next: Facets[K]) =>
    set({ [key]: value[key] === next ? undefined : next } as Partial<Facets>)

  return (
    <div className="browse-filters" role="group" aria-label="Filters">
      <div className="filter-row">
        <span className="filter-label">Rating</span>
        {RATINGS.map((stars) => (
          <button
            key={stars}
            type="button"
            className={`chip chip-btn ${value.min_rating === stars ? 'chip-on' : ''}`}
            aria-pressed={value.min_rating === stars}
            onClick={() => pick('min_rating', stars)}
          >
            {stars}★ & up
          </button>
        ))}
      </div>

      <div className="filter-row">
        <span className="filter-label">Price</span>
        {BANDS.map(({ value: band, label }) => (
          <button
            key={band}
            type="button"
            className={`chip chip-btn ${value.price_band === band ? 'chip-on' : ''}`}
            aria-pressed={value.price_band === band}
            onClick={() => pick('price_band', band)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="filter-row">
        <button
          type="button"
          className={`chip chip-btn ${value.vegetarian_only ? 'chip-on' : ''}`}
          aria-pressed={Boolean(value.vegetarian_only)}
          onClick={() => set({ vegetarian_only: !value.vegetarian_only })}
        >
          Vegetarian
        </button>
        <button
          type="button"
          className={`chip chip-btn ${value.open_only ? 'chip-on' : ''}`}
          aria-pressed={Boolean(value.open_only)}
          onClick={() => set({ open_only: !value.open_only })}
        >
          Open now
        </button>

        <label className="filter-sort">
          Sort
          <select
            className="input"
            value={value.sort ?? 'name'}
            onChange={(e) => set({ sort: e.target.value as RestaurantSort })}
          >
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  )
}
