import { useState } from 'react'
import type { FormEvent } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi } from '../../api/restaurants'
import type { MenuCategory, MenuItem } from '../../api/restaurants'
import { Alert, Button, ConfirmDialog } from '../../components/ui'
import { StockRow } from './StockRow'

interface CategoryPanelProps {
  restaurantId: number
  category: MenuCategory
  onChanged: () => void
  onEditItem: (item: MenuItem) => void
  onSetStock: (itemId: number, stock: number | null) => void
  onSetPrice: (itemId: number, price: number) => void
  onDeleteItem: (itemId: number) => void
  /** Uploads a dish photo straight from its row. */
  onPickItemImage?: (itemId: number, file: File) => void
}

/**
 * One section of the menu: its name, and its dishes as stock rows.
 *
 * The name doubles as the section marker in a single long list, so the list reads
 * as a menu — Grills, then Sides, then Desserts — rather than as one flat table
 * of dishes with a category column.
 */
export function CategoryPanel({
  restaurantId,
  category,
  onChanged,
  onEditItem,
  onSetStock,
  onSetPrice,
  onDeleteItem,
  onPickItemImage,
}: CategoryPanelProps) {
  const [renaming, setRenaming] = useState(false)
  const [name, setName] = useState(category.name)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function rename(e: FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed || trimmed === category.name) {
      setRenaming(false)
      return
    }
    setBusy(true)
    setError(null)
    try {
      await restaurantsApi.updateCategory(restaurantId, category.id, { name: trimmed })
      setRenaming(false)
      onChanged()
    } catch (err) {
      setError(errorMessage(err, 'Could not rename category.'))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    setError(null)
    try {
      await restaurantsApi.deleteCategory(restaurantId, category.id)
      setConfirmingDelete(false)
      onChanged()
    } catch (err) {
      // A 409 means the category still holds items; the API message names how
      // many, so surface it rather than a generic failure.
      setError(errorMessage(err, 'Could not delete category.'))
      setConfirmingDelete(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="menu-group" id={`category-${category.id}`}>
      <div className="menu-group-head">
        {renaming ? (
          <form className="owner-inline-form" onSubmit={rename}>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-label={`Rename ${category.name}`}
              autoFocus
              required
            />
            <Button variant="ghost" loading={busy}>Save</Button>
            <Button
              variant="ghost"
              type="button"
              onClick={() => {
                setName(category.name)
                setRenaming(false)
              }}
            >
              Cancel
            </Button>
          </form>
        ) : (
          <>
            <h3>{category.name}</h3>
            {/* Held back until hover or focus: renaming and deleting a whole
                category are rare next to editing a dish, and four live controls
                per section made the list look like a settings screen. */}
            <div className="menu-group-actions">
              <button
                className="link-btn"
                onClick={() => setRenaming(true)}
                aria-label={`Rename ${category.name}`}
              >
                Rename
              </button>
              <button
                className="link-danger"
                onClick={() => setConfirmingDelete(true)}
                aria-label={`Delete category ${category.name}`}
              >
                Delete
              </button>
            </div>
          </>
        )}
      </div>

      {error && <Alert>{error}</Alert>}

      <ConfirmDialog
        open={confirmingDelete}
        title={`Delete the "${category.name}" category?`}
        loading={busy}
        onCancel={() => setConfirmingDelete(false)}
        onConfirm={() => void remove()}
      />

      {category.items.length === 0 ? (
        <p className="muted menu-group-empty">Nothing in this section yet.</p>
      ) : (
        <div className="stock-list">
          {category.items.map((item) => (
            <StockRow
              key={item.id}
              item={item}
              onEdit={() => onEditItem(item)}
              onSetStock={(stock) => onSetStock(item.id, stock)}
              onSetPrice={(price) => onSetPrice(item.id, price)}
              onDelete={() => onDeleteItem(item.id)}
              onPickImage={
                onPickItemImage ? (file) => onPickItemImage(item.id, file) : undefined
              }
            />
          ))}
        </div>
      )}
    </section>
  )
}
