import { useCallback, useEffect, useState } from 'react'

import { ApiError } from '../api/client'
import { ordersApi } from '../api/orders'
import type { Order } from '../api/orders'
import { restaurantsApi } from '../api/restaurants'
import type { MenuItem, Restaurant, RestaurantDetail } from '../api/restaurants'
import { useAuth } from '../auth/AuthContext'
import { Alert, Button, ConfirmDialog, Field, Toast } from '../components/ui'
import { OrderOps } from '../components/OrderOps'
import { useTimedNotice, type ToastType } from '../lib/useTimedNotice'

export function OwnerPage() {
  const { user } = useAuth()
  const [mine, setMine] = useState<Restaurant[] | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const isOwner = user?.role === 'restaurant' || user?.role === 'admin'

  const loadMine = useCallback(async () => {
    if (!isOwner || !user) return
    try {
      const all = await restaurantsApi.list()
      const owned = all.filter((r) => r.owner_id === user.id || user.role === 'admin')
      setMine(owned)
      if (selectedId === null && owned.length > 0) setSelectedId(owned[0].id)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load your restaurants.')
    }
  }, [isOwner, user, selectedId])

  useEffect(() => {
    void loadMine()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOwner, user])

  if (!isOwner) {
    return (
      <main className="app-main">
        <h1>Manage</h1>
        <div className="empty">This area is for restaurant accounts.</div>
      </main>
    )
  }

  return (
    <main className="app-main">
      <h1>Manage your restaurants</h1>
      {error && <Alert>{error}</Alert>}

      <div className="owner-grid">
        <section className="owner-panel">
          <h2>Your restaurants</h2>
          {mine && mine.length > 0 ? (
            <div className="owner-rest-list">
              {mine.map((r) => (
                <button
                  key={r.id}
                  className="owner-rest-item"
                  data-active={r.id === selectedId}
                  onClick={() => setSelectedId(r.id)}
                >
                  <span>{r.name}</span>
                  <span className={`badge ${r.is_open ? 'badge-open' : 'badge-closed'}`}>
                    {r.is_open ? 'Open' : 'Closed'}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="muted">No restaurants yet. Create your first one.</p>
          )}
          <CreateRestaurantForm
            onCreated={async (r) => {
              await loadMine()
              setSelectedId(r.id)
            }}
          />
        </section>

        <section className="owner-panel">
          {selectedId === null ? (
            <div className="empty">Select or create a restaurant to manage its menu.</div>
          ) : (
            <>
              <IncomingOrders restaurantId={selectedId} />
              <MenuManager restaurantId={selectedId} onChanged={loadMine} />
            </>
          )}
        </section>
      </div>
    </main>
  )
}

function CreateRestaurantForm({ onCreated }: { onCreated: (r: Restaurant) => void }) {
  const [form, setForm] = useState({ name: '', city: '', address_line: '', phone: '', min_order_amount: '0' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function set(field: keyof typeof form) {
    return (e: { target: { value: string } }) => setForm((f) => ({ ...f, [field]: e.target.value }))
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const r = await restaurantsApi.create({
        name: form.name,
        city: form.city,
        address_line: form.address_line,
        phone: form.phone,
        min_order_amount: Number(form.min_order_amount) || 0,
      })
      setForm({ name: '', city: '', address_line: '', phone: '', min_order_amount: '0' })
      onCreated(r)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create restaurant.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="owner-form" onSubmit={submit}>
      <h3>New restaurant</h3>
      {error && <Alert>{error}</Alert>}
      <Field label="Name" value={form.name} onChange={set('name')} required />
      <Field label="City" value={form.city} onChange={set('city')} required />
      <Field label="Address" value={form.address_line} onChange={set('address_line')} required />
      <Field label="Phone" value={form.phone} onChange={set('phone')} required />
      <Field
        label="Minimum order amount"
        type="number"
        min="0"
        step="0.01"
        value={form.min_order_amount}
        onChange={set('min_order_amount')}
      />
      <Button block loading={busy}>Create restaurant</Button>
    </form>
  )
}

function MenuManager({ restaurantId, onChanged }: { restaurantId: number; onChanged: () => void }) {
  const [detail, setDetail] = useState<RestaurantDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { toast, showToast, clearToast } = useTimedNotice()
  const [categoryName, setCategoryName] = useState('')
  const [editingItemId, setEditingItemId] = useState<number | null>(null)
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)

  function clearFeedback() {
    setError(null)
    clearToast()
  }

  const load = useCallback(async () => {
    setError(null)
    try {
      setDetail(await restaurantsApi.get(restaurantId))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load menu.')
    }
  }, [restaurantId])

  useEffect(() => {
    void load()
  }, [load])

  async function toggleOpen() {
    if (!detail) return
    try {
      await restaurantsApi.update(restaurantId, { is_open: !detail.is_open })
      await load()
      onChanged()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not update.')
    }
  }

  async function addCategory(e: React.FormEvent) {
    e.preventDefault()
    if (!categoryName.trim()) return
    try {
      await restaurantsApi.addCategory(restaurantId, categoryName.trim())
      setCategoryName('')
      await load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not add category.')
    }
  }

  async function toggleItem(itemId: number, available: boolean) {
    try {
      await restaurantsApi.updateItem(restaurantId, itemId, { is_available: !available })
      await load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not update item.')
    }
  }

  function requestDelete(itemId: number) {
    clearFeedback()
    setPendingDeleteId(itemId)
  }

  async function confirmDelete() {
    if (pendingDeleteId === null) return
    setDeleteBusy(true)
    setError(null)
    try {
      await restaurantsApi.deleteItem(restaurantId, pendingDeleteId)
      setEditingItemId((id) => (id === pendingDeleteId ? null : id))
      setPendingDeleteId(null)
      showToast('delete')
      await load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not delete item.')
    } finally {
      setDeleteBusy(false)
    }
  }

  function handleItemSaved(type: ToastType) {
    setEditingItemId(null)
    setError(null)
    showToast(type)
    void load()
  }

  async function uploadRestaurantImage(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      await restaurantsApi.uploadImage(restaurantId, file)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Image upload failed.')
    }
  }

  async function uploadItemImage(itemId: number, e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      await restaurantsApi.uploadItemImage(restaurantId, itemId, file)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Image upload failed.')
    }
  }

  if (!detail) {
    return <div className="empty"><span className="spin" aria-hidden /> Loading…</div>
  }

  return (
    <div>
      <div className="owner-head">
        <h2>{detail.name}</h2>
        <Button variant="ghost" onClick={toggleOpen}>
          {detail.is_open ? 'Set closed' : 'Set open'}
        </Button>
      </div>
      {error && <Alert>{error}</Alert>}

      {toast && (
        <div className="toast-stack">
          <Toast type={toast.type} message={toast.message} />
        </div>
      )}

      <ConfirmDialog
        open={pendingDeleteId !== null}
        title="Delete Menu Item?"
        loading={deleteBusy}
        onCancel={() => setPendingDeleteId(null)}
        onConfirm={() => void confirmDelete()}
      />

      <div className="image-field">
        {detail.image_url ? (
          <img className="image-thumb" src={`/api${detail.image_url}`} alt={`${detail.name} cover`} />
        ) : (
          <div className="image-thumb image-placeholder" aria-hidden>No image</div>
        )}
        <label className="file-label">
          {detail.image_url ? 'Replace cover image' : 'Upload cover image'}
          <input type="file" accept="image/*" onChange={uploadRestaurantImage} />
        </label>
      </div>

      <form className="owner-inline-form" onSubmit={addCategory}>
        <input
          className="input"
          placeholder="New category (e.g. Mains)"
          value={categoryName}
          onChange={(e) => setCategoryName(e.target.value)}
          aria-label="New category name"
        />
        <Button variant="ghost">Add category</Button>
      </form>

      {detail.menu.length === 0 ? (
        <p className="muted">No categories yet. Add one to start building your menu.</p>
      ) : (
        detail.menu.map((cat) => (
          <section key={cat.id} className="menu-section">
            <h3>{cat.name}</h3>
            <div className="menu-items">
              {cat.items.map((item) => (
                <div key={item.id}>
                  <div className="menu-item">
                    <div className="menu-item-lead">
                      {item.image_url ? (
                        <img className="item-thumb" src={`/api${item.image_url}`} alt={item.name} />
                      ) : (
                        <div className="item-thumb item-placeholder" aria-hidden>🍽</div>
                      )}
                      <div>
                        <div className="menu-item-name">{item.name}</div>
                        <div className="muted">${Number(item.price).toFixed(2)}</div>
                      </div>
                    </div>
                    <div className="menu-item-actions">
                      <label className="file-label file-label-sm">
                        Photo
                        <input type="file" accept="image/*" onChange={(e) => uploadItemImage(item.id, e)} />
                      </label>
                      <button
                        className="link-btn"
                        onClick={() => {
                          clearFeedback()
                          setEditingItemId(item.id)
                        }}
                      >
                        Edit
                      </button>
                      <button
                        className="link-danger"
                        onClick={() => toggleItem(item.id, item.is_available)}
                      >
                        {item.is_available ? 'Mark unavailable' : 'Mark available'}
                      </button>
                      <button
                        className="link-danger"
                        onClick={() => requestDelete(item.id)}
                        aria-label={`Delete ${item.name}`}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                  {editingItemId === item.id && (
                    <ItemForm
                      key={item.id}
                      restaurantId={restaurantId}
                      categoryId={cat.id}
                      item={item}
                      onDone={handleItemSaved}
                      onCancel={() => setEditingItemId(null)}
                    />
                  )}
                </div>
              ))}
            </div>
            <ItemForm restaurantId={restaurantId} categoryId={cat.id} onDone={handleItemSaved} />
          </section>
        ))
      )}
    </div>
  )
}

function IncomingOrders({ restaurantId }: { restaurantId: number }) {
  const [orders, setOrders] = useState<Order[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setOrders(await ordersApi.forRestaurant(restaurantId))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load orders.')
    }
  }, [restaurantId])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <section className="menu-section">
      <div className="owner-head">
        <h2>Incoming orders</h2>
        <Button variant="ghost" onClick={load}>Refresh</Button>
      </div>
      {error && <Alert>{error}</Alert>}
      {!orders ? (
        <div className="empty"><span className="spin" aria-hidden /> Loading…</div>
      ) : (
        <OrderOps orders={orders} onChanged={load} />
      )}
    </section>
  )
}

function ItemForm({
  restaurantId,
  categoryId,
  item,
  onDone,
  onCancel,
}: {
  restaurantId: number
  categoryId: number
  item?: MenuItem
  onDone: (type: ToastType) => void
  onCancel?: () => void
}) {
  const isEdit = item != null
  const [name, setName] = useState(item?.name ?? '')
  const [price, setPrice] = useState(item ? String(item.price) : '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (isEdit) {
        await restaurantsApi.updateItem(restaurantId, item.id, {
          name: name.trim(),
          price: Number(price),
        })
        onDone('edit')
      } else {
        await restaurantsApi.addItem(restaurantId, {
          category_id: categoryId,
          name: name.trim(),
          price: Number(price),
        })
        setName('')
        setPrice('')
        onDone('add')
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Could not ${isEdit ? 'update' : 'add'} item.`)
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
      {error && <Alert>{error}</Alert>}
      <Button variant="ghost" loading={busy}>{isEdit ? 'Save' : 'Add item'}</Button>
      {isEdit && onCancel && (
        <Button variant="ghost" type="button" onClick={onCancel}>Cancel</Button>
      )}
    </form>
  )
}
