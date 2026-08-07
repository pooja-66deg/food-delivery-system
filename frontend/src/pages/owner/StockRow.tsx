import { useEffect, useState } from 'react'

import type { MenuItem } from '../../api/restaurants'

interface StockRowProps {
  item: MenuItem
  /** Open the full editor — name, photo, diet, visibility. */
  onEdit: () => void
  onSetStock: (stock: number | null) => void
  onSetPrice: (price: number) => void
  onDelete: () => void
}

/**
 * One dish as a stock-and-price row.
 *
 * These two are what an owner changes during a service — a dish runs low, a price
 * moves — so they are editable in place. Everything else about a dish (its name,
 * photo, diet flag, whether it is listed at all) is a rarer edit and lives behind
 * the row's name in a dialog, which keeps the row itself readable.
 */
export function StockRow({ item, onEdit, onSetStock, onSetPrice, onDelete }: StockRowProps) {
  // Local copies so typing is not fighting a refetch. Reset when the row's own
  // item changes, so a save elsewhere on the page is reflected here.
  const [price, setPrice] = useState(String(item.price))
  useEffect(() => setPrice(String(item.price)), [item.price])

  const tracked = item.stock_quantity !== null

  function commitPrice() {
    const next = Number(price)
    // Reject blank and nonsense rather than sending NaN; the row springs back.
    if (!Number.isFinite(next) || next <= 0) {
      setPrice(String(item.price))
      return
    }
    if (next !== Number(item.price)) onSetPrice(next)
  }

  return (
    <div className="stock-row" data-hidden={!item.is_available || undefined}>
      <div className="stock-row-lead">
        {/* The name is the way into the full editor: it is the thing an owner
            points at when they mean "this dish". */}
        <button type="button" className="stock-row-name" onClick={onEdit}>
          {item.name}
        </button>
        <p className="muted stock-row-note">
          {tracked ? `${item.stock_quantity} in stock` : 'Stock not tracked'}
          {!item.is_available && ' · hidden from diners'}
          {item.is_available && tracked && item.stock_quantity === 0 && ' · sold out'}
        </p>
      </div>

      <div className="stepper">
        <button
          type="button"
          className="stepper-btn"
          aria-label={`Decrease stock of ${item.name}`}
          // Nothing to decrease from when stock is untracked or already zero.
          disabled={!tracked || item.stock_quantity === 0}
          onClick={() => onSetStock((item.stock_quantity ?? 0) - 1)}
        >
          −
        </button>
        <span className="stepper-value" aria-label={`Stock of ${item.name}`}>
          {tracked ? item.stock_quantity : '—'}
        </span>
        <button
          type="button"
          className="stepper-btn"
          aria-label={`Increase stock of ${item.name}`}
          // From untracked, the first + starts tracking at one rather than
          // jumping to a number the owner never chose.
          onClick={() => onSetStock(tracked ? (item.stock_quantity ?? 0) + 1 : 1)}
        >
          +
        </button>
      </div>

      <label className="stock-row-amount">
        <span className="muted">Amount</span>
        <input
          className="input"
          type="number"
          min="0.01"
          step="0.01"
          value={price}
          aria-label={`Price of ${item.name}`}
          onChange={(e) => setPrice(e.target.value)}
          onBlur={commitPrice}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              commitPrice()
            }
          }}
        />
      </label>

      <span className="stock-row-total">₹{Number(item.price).toFixed(2)}</span>

      <button
        type="button"
        className="icon-danger"
        aria-label={`Delete ${item.name}`}
        onClick={onDelete}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path
            d="M5 7h14M10 7V5h4v2M6.5 7l.8 12h9.4l.8-12M10.5 10.5v5M13.5 10.5v5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </div>
  )
}
