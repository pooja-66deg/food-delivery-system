import type { CuisineCount } from '../api/restaurants'

interface PopularCuisinesProps {
  cuisines: CuisineCount[]
  onPick: (cuisine: string) => void
}

/**
 * Discovery chips for the busiest cuisines. Presentational — the page owns
 * fetching, so this stays trivial to test and reuse.
 *
 * Renders nothing when empty, so a database with no tagged restaurants shows
 * no stray "Popular" label with an empty row beside it.
 */
export function PopularCuisines({ cuisines, onPick }: PopularCuisinesProps) {
  if (cuisines.length === 0) return null

  return (
    <div className="cuisine-row">
      <span className="cuisine-label">Popular</span>
      {cuisines.map(({ cuisine, count }) => (
        <button
          key={cuisine}
          type="button"
          className="chip chip-button"
          title={`${count} restaurant${count === 1 ? '' : 's'}`}
          onClick={() => onPick(cuisine)}
        >
          {cuisine}
        </button>
      ))}
    </div>
  )
}
