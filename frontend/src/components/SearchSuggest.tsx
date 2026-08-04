import { useEffect, useId, useRef, useState } from 'react'

import type { RestaurantSuggestion } from '../api/restaurants'
import { useDebouncedValue } from '../lib/useDebouncedValue'

/** Matches SUGGEST_MIN_CHARS in src/modules/restaurants/service.py. */
const MIN_CHARS = 2

interface SearchSuggestProps {
  value: string
  onChange: (value: string) => void
  onSelect: (suggestion: RestaurantSuggestion) => void
  fetchSuggestions: (q: string) => Promise<RestaurantSuggestion[]>
  placeholder?: string
  debounceMs?: number
}

/**
 * Restaurant typeahead following the ARIA combobox pattern: the input owns the
 * `combobox` role and points at the active option via `aria-activedescendant`,
 * so screen readers announce the highlighted suggestion without moving focus
 * off the input.
 */
export function SearchSuggest({
  value,
  onChange,
  onSelect,
  fetchSuggestions,
  placeholder = 'Search restaurants…',
  debounceMs = 250,
}: SearchSuggestProps) {
  const listId = useId()
  const [items, setItems] = useState<RestaurantSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)

  const term = useDebouncedValue(value.trim(), debounceMs)

  // Held in a ref so an unstable `fetchSuggestions` identity (an inline arrow
  // from the parent) cannot retrigger the effect on every render.
  const fetchRef = useRef(fetchSuggestions)
  fetchRef.current = fetchSuggestions

  useEffect(() => {
    if (term.length < MIN_CHARS) {
      setItems([])
      setOpen(false)
      return
    }

    // `stale` guards against an earlier, slower response landing after a newer
    // one and replacing fresher suggestions.
    let stale = false
    void fetchRef
      .current(term)
      .then((results) => {
        if (stale) return
        setItems(results)
        setOpen(results.length > 0)
        setActiveIndex(-1)
      })
      .catch(() => {
        if (stale) return
        setItems([])
        setOpen(false)
      })

    return () => {
      stale = true
    }
  }, [term])

  const choose = (suggestion: RestaurantSuggestion) => {
    setOpen(false)
    setActiveIndex(-1)
    onSelect(suggestion)
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || items.length === 0) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => (i + 1) % items.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => (i <= 0 ? items.length - 1 : i - 1))
    } else if (e.key === 'Enter') {
      if (activeIndex >= 0) {
        e.preventDefault()
        choose(items[activeIndex])
      }
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
      setActiveIndex(-1)
    }
  }

  const optionId = (index: number) => `${listId}-option-${index}`
  const expanded = open && items.length > 0

  return (
    <div className="suggest">
      <input
        className="input"
        role="combobox"
        // A placeholder is not an accessible name: it is not exposed to every
        // screen reader and vanishes once typing starts. The page also has other
        // comboboxes now (the sort select), so this box needs to be nameable.
        aria-label={placeholder}
        aria-expanded={expanded}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={expanded && activeIndex >= 0 ? optionId(activeIndex) : undefined}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
      />

      {expanded && (
        <ul className="suggest-list" id={listId} role="listbox">
          {items.map((s, i) => (
            <li
              key={s.id}
              id={optionId(i)}
              role="option"
              aria-selected={i === activeIndex}
              className="suggest-option"
              data-active={i === activeIndex}
              // onMouseDown, not onClick: it fires before the input's blur, so
              // the list is still mounted when the choice is registered.
              onMouseDown={(e) => {
                e.preventDefault()
                choose(s)
              }}
              onMouseEnter={() => setActiveIndex(i)}
            >
              <span className="suggest-name">{s.name}</span>
              <span className="suggest-meta">
                {[s.cuisine, s.city].filter(Boolean).join(' · ')}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
