import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi } from '../../api/restaurants'
import type { MenuItem, RestaurantDetail } from '../../api/restaurants'
import { Alert, ConfirmDialog, EmptyState, Loading, Modal, Toast } from '../../components/ui'
import { useTimedNotice, type ToastType } from '../../lib/useTimedNotice'
import { CategoryPanel } from './CategoryPanel'
import { ItemForm } from './ItemForm'
import { AddCategoryCard, AddItemCard } from './MenuForms'
import { RestaurantSettings } from './RestaurantSettings'
import { dishCount, plural } from './ownerStats'

/**
 * One restaurant, opened from the dashboard.
 *
 * A single scrolling page rather than tabs: the two create forms sit at the top
 * where an owner starts, the menu reads below them as a menu does, and the
 * restaurant's own settings close it out. Everything here mutates through this
 * component so there is one refetch and one source of truth for the menu.
 */
export function RestaurantWorkspace({
  restaurantId,
  ordersToday,
  onBack,
  onChanged,
}: {
  restaurantId: number
  /** Counted by the dashboard, which already holds every restaurant's orders. */
  ordersToday: number
  onBack: () => void
  /** Refetch the dashboard, so its tiles and rows follow an edit here. */
  onChanged: () => void
}) {
  const [detail, setDetail] = useState<RestaurantDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { toast, showToast, clearToast } = useTimedNotice()
  const [categoryBusy, setCategoryBusy] = useState(false)
  const [itemBusy, setItemBusy] = useState(false)
  const [editing, setEditing] = useState<MenuItem | null>(null)
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setDetail(await restaurantsApi.get(restaurantId))
      setError(null)
    } catch (e) {
      setError(errorMessage(e, 'Failed to load this restaurant.'))
    }
  }, [restaurantId])

  useEffect(() => {
    void load()
  }, [load])

  /** Every mutation goes through here: reload this page, then the dashboard. */
  async function mutate(action: () => Promise<unknown>, failure: string) {
    setError(null)
    try {
      await action()
      await load()
      onChanged()
      return true
    } catch (e) {
      setError(errorMessage(e, failure))
      return false
    }
  }

  async function addCategory(name: string) {
    setCategoryBusy(true)
    await mutate(() => restaurantsApi.addCategory(restaurantId, name), 'Could not add category.')
    setCategoryBusy(false)
  }

  async function addItem(fields: {
    name: string
    categoryId: number
    stock: number | null
    price: number
    image: File | null
  }) {
    setItemBusy(true)
    const ok = await mutate(
      async () => {
        const item = await restaurantsApi.addItem(restaurantId, {
          category_id: fields.categoryId,
          name: fields.name,
          price: fields.price,
          stock_quantity: fields.stock,
        })
        if (fields.image) {
          await restaurantsApi.uploadItemImage(restaurantId, item.id, fields.image)
        }
      },
      'Could not add item.',
    )
    if (ok) showToast('add')
    setItemBusy(false)
  }

  async function confirmDelete() {
    if (pendingDeleteId === null) return
    setDeleteBusy(true)
    const ok = await mutate(
      () => restaurantsApi.deleteItem(restaurantId, pendingDeleteId),
      'Could not delete item.',
    )
    if (ok) {
      setPendingDeleteId(null)
      showToast('delete')
    }
    setDeleteBusy(false)
  }

  function handleItemSaved(type: ToastType) {
    setEditing(null)
    showToast(type)
    void load()
    onChanged()
  }

  if (!detail && error) {
    return (
      <>
        <BackLink onBack={onBack} />
        <Alert>{error}</Alert>
      </>
    )
  }
  if (!detail) return <Loading />

  const dishes = dishCount(detail)

  return (
    <>
      <BackLink onBack={onBack} />

      <header className="venue-hero">
        <div className="venue-hero-text">
          <h1>{detail.name}</h1>
          <p className="muted">
            {detail.cuisine ? `${detail.cuisine} · ` : ''}
            {plural(dishes, 'item')} · {plural(ordersToday, 'order')} today
          </p>
        </div>
        {/* Jump links, not filters: on a long menu they save the scroll to a
            section without hiding the rest of it. */}
        {detail.menu.length > 0 && (
          <nav className="venue-jump" aria-label="Jump to a category">
            {detail.menu.map((cat) => (
              <a key={cat.id} href={`#category-${cat.id}`} className="jump-chip">
                {cat.name}
              </a>
            ))}
          </nav>
        )}
      </header>

      {error && <Alert>{error}</Alert>}

      {toast && (
        <div className="toast-stack">
          <Toast type={toast.type} message={toast.message} />
        </div>
      )}

      <div className="compose-row">
        <AddCategoryCard busy={categoryBusy} onAdd={(name) => void addCategory(name)} />
        <AddItemCard
          categories={detail.menu}
          busy={itemBusy}
          onAdd={(fields) => void addItem(fields)}
        />
      </div>

      <ConfirmDialog
        open={pendingDeleteId !== null}
        title="Delete this dish?"
        loading={deleteBusy}
        onCancel={() => setPendingDeleteId(null)}
        onConfirm={() => void confirmDelete()}
      />

      {/* The full editor for the rarer fields — name, photo, diet, visibility —
          which would crowd a row that is about stock and price. */}
      <Modal
        open={editing !== null}
        title={editing ? `Edit ${editing.name}` : 'Edit dish'}
        onClose={() => setEditing(null)}
      >
        {editing && (
          <ItemForm
            key={editing.id}
            restaurantId={restaurantId}
            categoryId={editing.category_id}
            item={editing}
            onDone={handleItemSaved}
            onCancel={() => setEditing(null)}
            onPickImage={(file) =>
              void mutate(
                () => restaurantsApi.uploadItemImage(restaurantId, editing.id, file),
                'Image upload failed.',
              )
            }
            onToggleAvailable={() =>
              void mutate(
                () =>
                  restaurantsApi.updateItem(restaurantId, editing.id, {
                    is_available: !editing.is_available,
                  }),
                'Could not update item.',
              )
            }
          />
        )}
      </Modal>

      <section className="menu-stock">
        <h2>Menu &amp; stock</h2>

        {detail.menu.length === 0 ? (
          <EmptyState>
            No categories yet. Add one above — like Starters or Mains — to start building your menu.
          </EmptyState>
        ) : (
          detail.menu.map((cat) => (
            <CategoryPanel
              key={cat.id}
              restaurantId={restaurantId}
              category={cat}
              onChanged={() => {
                void load()
                onChanged()
              }}
              onEditItem={setEditing}
              onPickItemImage={(itemId, file) =>
                void mutate(
                  () => restaurantsApi.uploadItemImage(restaurantId, itemId, file),
                  'Image upload failed.',
                )
              }
              onSetStock={(itemId, stock) =>
                void mutate(
                  () => restaurantsApi.updateItem(restaurantId, itemId, { stock_quantity: stock }),
                  'Could not update stock.',
                )
              }
              onSetPrice={(itemId, price) =>
                void mutate(
                  () => restaurantsApi.updateItem(restaurantId, itemId, { price }),
                  'Could not update price.',
                )
              }
              onDeleteItem={(itemId) => {
                clearToast()
                setPendingDeleteId(itemId)
              }}
            />
          ))
        )}
      </section>

      <section className="venue-settings">
        <h2>Restaurant settings</h2>
        <div className="owner-panel">
          <RestaurantSettings
            detail={detail}
            onChanged={() => {
              void load()
              onChanged()
            }}
          />
        </div>
      </section>
    </>
  )
}

function BackLink({ onBack }: { onBack: () => void }) {
  return (
    <button type="button" className="venue-back" onClick={onBack}>
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path
          d="M19 12H5m0 0 6-6m-6 6 6 6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      All restaurants
    </button>
  )
}
