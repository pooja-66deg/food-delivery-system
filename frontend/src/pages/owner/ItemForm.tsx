import { useState } from 'react'
import type { FormEvent } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi } from '../../api/restaurants'
import type { MenuItem, MenuItemCreateInput } from '../../api/restaurants'
import { Alert, Button, Field, FilePicker, Thumb } from '../../components/ui'
import type { ToastType } from '../../lib/useTimedNotice'

interface ItemFormProps {
  restaurantId: number
  categoryId: number
  /** Present when editing an existing item. */
  item?: MenuItem
  onDone: (type: ToastType) => void
  onCancel?: () => void
  /** Editing only: the photo and visibility save on their own, not on submit. */
  onPickImage?: (file: File) => void
  onToggleAvailable?: () => void
}

/** Blank stock means "don't track" — the API takes null for that. */
function toStock(raw: string): number | null {
  const trimmed = raw.trim()
  return trimmed === '' ? null : Number(trimmed)
}

export function ItemForm({
  restaurantId,
  categoryId,
  item,
  onDone,
  onCancel,
  onPickImage,
  onToggleAvailable,
}: ItemFormProps) {
  const isEdit = item != null
  const [name, setName] = useState(item?.name ?? '')
  const [price, setPrice] = useState(item ? String(item.price) : '')
  const [stock, setStock] = useState(
    item?.stock_quantity == null ? '' : String(item.stock_quantity),
  )
  const [vegetarian, setVegetarian] = useState(item?.is_vegetarian ?? false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    const fields: Omit<MenuItemCreateInput, 'category_id'> = {
      name: name.trim(),
      price: Number(price),
      stock_quantity: toStock(stock),
      is_vegetarian: vegetarian,
    }
    try {
      if (isEdit) {
        await restaurantsApi.updateItem(restaurantId, item.id, fields)
        onDone('edit')
      } else {
        await restaurantsApi.addItem(restaurantId, { category_id: categoryId, ...fields })
        setName('')
        setPrice('')
        setStock('')
        setVegetarian(false)
        onDone('add')
      }
    } catch (err) {
      setError(errorMessage(err, `Could not ${isEdit ? 'update' : 'add'} item.`))
    } finally {
      setBusy(false)
    }
  }

  // Stacked with real labels rather than a row of placeholder-only inputs: this
  // now opens in a dialog, and "Price"/"Stock" side by side gave no way to tell
  // which box was which once you had typed in them.
  return (
    <form className="owner-form" onSubmit={submit}>
      {error && <Alert>{error}</Alert>}
      <Field
        label="Item name"
        name="item_name"
        placeholder="e.g. Margherita"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
        required
      />
      <div className="field-row">
        <Field
          label="Item price"
          name="item_price"
          type="number"
          min="0.01"
          step="0.01"
          placeholder="0.00"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          required
        />
        <Field
          label="Stock quantity"
          name="stock_quantity"
          type="number"
          min="0"
          step="1"
          placeholder="Untracked"
          value={stock}
          onChange={(e) => setStock(e.target.value)}
        />
      </div>
      <p className="muted field-note">
        Leave stock blank to sell without tracking it. Zero means sold out.
      </p>
      <label className="check-inline" title="Shown to diners filtering for vegetarian food">
        <input
          type="checkbox"
          checked={vegetarian}
          onChange={(e) => setVegetarian(e.target.checked)}
        />
        Vegetarian
      </label>

      {/* The photo and the listing switch act immediately rather than waiting for
          submit: both are one decision, and pairing them with a Save that also
          carries the name and price made it unclear what was pending. */}
      {item && (onPickImage || onToggleAvailable) && (
        <div className="item-extras">
          {onPickImage && (
            <div className="item-extras-photo">
              <Thumb url={item.image_url} alt={item.name} />
              <FilePicker
                label={item.image_url ? 'Replace photo' : 'Add photo'}
                small
                onPick={onPickImage}
              />
            </div>
          )}
          {onToggleAvailable && (
            <Button variant="ghost" type="button" onClick={onToggleAvailable}>
              {item.is_available ? 'Hide from diners' : 'Show to diners'}
            </Button>
          )}
        </div>
      )}

      <div className="form-actions">
        {onCancel && (
          <Button variant="ghost" type="button" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button loading={busy}>{isEdit ? 'Save' : 'Add item'}</Button>
      </div>
    </form>
  )
}
