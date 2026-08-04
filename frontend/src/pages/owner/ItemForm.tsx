import { useState } from 'react'
import type { FormEvent } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi } from '../../api/restaurants'
import type { MenuItem, MenuItemCreateInput } from '../../api/restaurants'
import { Alert, Button } from '../../components/ui'
import type { ToastType } from '../../lib/useTimedNotice'

interface ItemFormProps {
  restaurantId: number
  categoryId: number
  /** Present when editing an existing item. */
  item?: MenuItem
  onDone: (type: ToastType) => void
  onCancel?: () => void
}

/** Blank stock means "don't track" — the API takes null for that. */
function toStock(raw: string): number | null {
  const trimmed = raw.trim()
  return trimmed === '' ? null : Number(trimmed)
}

export function ItemForm({ restaurantId, categoryId, item, onDone, onCancel }: ItemFormProps) {
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

  return (
    <form className="owner-inline-form" onSubmit={submit}>
      <input
        className="input"
        placeholder="Item name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        aria-label="Item name"
        required
      />
      <input
        className="input input-narrow"
        placeholder="Price"
        type="number"
        min="0.01"
        step="0.01"
        value={price}
        onChange={(e) => setPrice(e.target.value)}
        aria-label="Item price"
        required
      />
      <input
        className="input input-narrow"
        placeholder="Stock"
        type="number"
        min="0"
        step="1"
        value={stock}
        onChange={(e) => setStock(e.target.value)}
        aria-label="Stock quantity"
        title="Leave blank to sell without tracking stock"
      />
      <label className="check-inline" title="Shown to diners filtering for vegetarian food">
        <input
          type="checkbox"
          checked={vegetarian}
          onChange={(e) => setVegetarian(e.target.checked)}
        />
        Vegetarian
      </label>
      {error && <Alert>{error}</Alert>}
      <Button variant="ghost" loading={busy}>{isEdit ? 'Save' : 'Add item'}</Button>
      {isEdit && onCancel && (
        <Button variant="ghost" type="button" onClick={onCancel}>Cancel</Button>
      )}
    </form>
  )
}
