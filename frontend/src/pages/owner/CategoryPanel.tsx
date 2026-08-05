import { useState } from 'react'
import type { FormEvent } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi } from '../../api/restaurants'
import type { MenuCategory } from '../../api/restaurants'
import { Alert, Button, ConfirmDialog } from '../../components/ui'
import type { ToastType } from '../../lib/useTimedNotice'
import { ItemForm } from './ItemForm'
import { MenuItemPanel } from './MenuItemPanel'

interface CategoryPanelProps {
  restaurantId: number
  category: MenuCategory
  onChanged: () => void
  onItemSaved: (type: ToastType) => void
  onDeleteItem: (itemId: number) => void
  onToggleItem: (itemId: number, available: boolean) => void
  onPickItemImage: (itemId: number, file: File) => void
  /** Item currently open for editing, if it belongs to this category. */
  editingItemId: number | null
  onEditItem: (itemId: number | null) => void
}

export function CategoryPanel({
  restaurantId,
  category,
  onChanged,
  onItemSaved,
  onDeleteItem,
  onToggleItem,
  onPickItemImage,
  editingItemId,
  onEditItem,
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
    <section className="menu-section">
      <div className="owner-head">
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
            <div className="menu-item-actions">
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

      <div className="menu-grid">
        {category.items.map((item) => (
          <div key={item.id} className="menu-item-card">
            <MenuItemPanel
              item={item}
              onEdit={() => onEditItem(item.id)}
              onToggleAvailable={() => onToggleItem(item.id, item.is_available)}
              onDelete={() => onDeleteItem(item.id)}
              onPickImage={(file) => onPickItemImage(item.id, file)}
            />
            {editingItemId === item.id && (
              <ItemForm
                key={item.id}
                restaurantId={restaurantId}
                categoryId={category.id}
                item={item}
                onDone={onItemSaved}
                onCancel={() => onEditItem(null)}
              />
            )}
          </div>
        ))}
      </div>

      <ItemForm restaurantId={restaurantId} categoryId={category.id} onDone={onItemSaved} />
    </section>
  )
}
