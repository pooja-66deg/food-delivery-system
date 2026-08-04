import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi } from '../../api/restaurants'
import type { RestaurantDetail } from '../../api/restaurants'
import { Alert, Button, ConfirmDialog, FilePicker, Loading, Thumb, Toast } from '../../components/ui'
import { useTimedNotice, type ToastType } from '../../lib/useTimedNotice'
import { CategoryPanel } from './CategoryPanel'
import { DeliveryZonePanel } from './DeliveryZonePanel'

export function MenuManager({
  restaurantId,
  onChanged,
}: {
  restaurantId: number
  onChanged: () => void
}) {
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
      setError(errorMessage(e, 'Failed to load menu.'))
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
      setError(errorMessage(e, 'Could not update.'))
    }
  }

  async function addCategory(e: FormEvent) {
    e.preventDefault()
    if (!categoryName.trim()) return
    try {
      await restaurantsApi.addCategory(restaurantId, categoryName.trim())
      setCategoryName('')
      await load()
    } catch (e) {
      setError(errorMessage(e, 'Could not add category.'))
    }
  }

  async function toggleItem(itemId: number, available: boolean) {
    try {
      await restaurantsApi.updateItem(restaurantId, itemId, { is_available: !available })
      await load()
    } catch (e) {
      setError(errorMessage(e, 'Could not update item.'))
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
      setError(errorMessage(e, 'Could not delete item.'))
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

  async function uploadCoverImage(file: File) {
    try {
      await restaurantsApi.uploadImage(restaurantId, file)
      await load()
    } catch (err) {
      setError(errorMessage(err, 'Image upload failed.'))
    }
  }

  async function uploadItemImage(itemId: number, file: File) {
    try {
      await restaurantsApi.uploadItemImage(restaurantId, itemId, file)
      await load()
    } catch (err) {
      setError(errorMessage(err, 'Image upload failed.'))
    }
  }

  if (!detail) return <Loading />

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
        <Thumb url={detail.image_url} alt={`${detail.name} cover`} variant="cover" />
        <FilePicker
          label={detail.image_url ? 'Replace cover image' : 'Upload cover image'}
          onPick={(file) => void uploadCoverImage(file)}
        />
      </div>

      <DeliveryZonePanel
        restaurantId={restaurantId}
        radiusKm={detail.delivery_radius_km}
        onSaved={() => {
          void load()
          onChanged()
        }}
      />

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
          <CategoryPanel
            key={cat.id}
            restaurantId={restaurantId}
            category={cat}
            onChanged={load}
            onItemSaved={handleItemSaved}
            onDeleteItem={requestDelete}
            onToggleItem={toggleItem}
            onPickItemImage={(itemId, file) => void uploadItemImage(itemId, file)}
            editingItemId={editingItemId}
            onEditItem={(itemId) => {
              clearFeedback()
              setEditingItemId(itemId)
            }}
          />
        ))
      )}
    </div>
  )
}
