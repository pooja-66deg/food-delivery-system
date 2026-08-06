import { useState } from 'react'
import type { FormEvent } from 'react'

import type { MenuCategory } from '../../api/restaurants'
import { Button, Field } from '../../components/ui'

/** A "+" for the create buttons, so both read as additive at a glance. */
function PlusIcon() {
  return (
    <svg className="btn-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M12 6v12M6 12h12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

export function AddCategoryCard({
  busy,
  onAdd,
}: {
  busy: boolean
  onAdd: (name: string) => void
}) {
  const [name, setName] = useState('')

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    onAdd(name.trim())
    setName('')
  }

  return (
    <form className="compose-card" onSubmit={submit}>
      <h2>Add category</h2>
      <Field
        label="Category name"
        name="category_name"
        placeholder="e.g. Desserts"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <Button block loading={busy}>
        <PlusIcon /> Add category
      </Button>
    </form>
  )
}

const EMPTY = { name: '', categoryId: '', stock: '', price: '' }

export function AddItemCard({
  categories,
  busy,
  onAdd,
}: {
  categories: MenuCategory[]
  busy: boolean
  onAdd: (fields: { name: string; categoryId: number; stock: number | null; price: number }) => void
}) {
  const [form, setForm] = useState(EMPTY)

  function set(field: keyof typeof form) {
    return (e: { target: { value: string } }) => setForm((f) => ({ ...f, [field]: e.target.value }))
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    onAdd({
      name: form.name.trim(),
      categoryId: Number(form.categoryId),
      // Blank means "sell it without tracking stock", which the API models as null.
      stock: form.stock.trim() === '' ? null : Number(form.stock),
      price: Number(form.price),
    })
    setForm(EMPTY)
  }

  // Nowhere to put a dish yet. Said plainly rather than showing a form whose
  // category picker is empty and whose submit can never succeed.
  if (categories.length === 0) {
    return (
      <div className="compose-card">
        <h2>Add item</h2>
        <p className="muted">Add a category first — every dish belongs to one.</p>
      </div>
    )
  }

  return (
    <form className="compose-card" onSubmit={submit}>
      <h2>Add item</h2>
      <div className="compose-grid">
        <Field
          label="Item name"
          name="item_name"
          placeholder="e.g. Basque Cheesecake"
          value={form.name}
          onChange={set('name')}
          required
        />
        <div className="field">
          <label htmlFor="item_category">Category</label>
          <select
            id="item_category"
            name="item_category"
            className="input"
            value={form.categoryId}
            onChange={set('categoryId')}
            required
          >
            <option value="">Pick a category</option>
            {categories.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {cat.name}
              </option>
            ))}
          </select>
        </div>
        <Field
          label="Stock"
          name="item_stock"
          type="number"
          min="0"
          step="1"
          placeholder="Leave blank to not track"
          value={form.stock}
          onChange={set('stock')}
        />
        <Field
          label="Amount"
          name="item_price"
          type="number"
          min="0.01"
          step="0.01"
          placeholder="0.00"
          value={form.price}
          onChange={set('price')}
          required
        />
      </div>
      <div className="compose-actions">
        <Button loading={busy}>
          <PlusIcon /> Add item
        </Button>
      </div>
    </form>
  )
}
