# Design — Merchant catalog & inventory

Date: 2026-08-03
Branch: `feat/merchant-catalog`
Phase: E (see `2026-07-31-auth-forms-and-role-routing-design.md`)
Status: approved, implementing

## Problem

Phase E covers four items. Two already landed:

| Item | State before this branch |
| --- | --- |
| Menu item edit/delete | **Done** — `PATCH`/`DELETE /restaurants/{id}/items/{item_id}` with owner UI (commit 10b90c9). |
| Category update/delete | **Missing** — `menu.py` has `add_category` and `list_categories` only. A typo in a category name is permanent. |
| Image display | **Half** — upload and owner-side thumbnails exist. `image_url` appears nowhere in the customer pages, so uploaded images are invisible to the people they are for. |
| Inventory | **Missing** — no stock column. The checkout gate reads only the manual `is_available` flag, so a restaurant can sell the same last portion any number of times. |

## Decisions

- **Stock is nullable and availability is derived.** `stock_quantity IS NULL`
  means "not tracked", so every existing item behaves exactly as before.
  `is_available` stays the owner's manual switch and the system never rewrites
  it, which keeps "the owner turned this off" distinguishable from "we sold
  out" — and makes a restock a one-field edit with nothing to un-flip.
- **Stock moves on order and comes back on cancel.** Without the restore, every
  cancelled order silently leaks stock and the counter stops being worth
  reading.
- **Deleting a category that still holds items is refused (409)**, not
  cascaded. An accidental click must not erase a menu section. The owner deletes
  or moves the items first.

## Data model

One migration, `menu_items` only:

| Column | Type | Notes |
| --- | --- | --- |
| `stock_quantity` | `Integer`, nullable | Null = untracked. No server default, so existing rows read as untracked. |

`MenuItemResponse` gains `stock_quantity: int | None` and a computed
`in_stock: bool`:

```
in_stock = is_available and (stock_quantity is None or stock_quantity > 0)
```

Customers read `in_stock` alone to decide whether ordering is possible; the
owner UI reads the two raw fields. `MenuItemCreate` and `MenuItemUpdate` accept
`stock_quantity` with `ge=0`.

## Backend

### `src/modules/restaurants/inventory.py` (new)

Stock movement lives in one module so neither the cart nor the orders domain
grows inventory logic of its own:

- `shortfall(item, quantity) -> bool` — whether a line exceeds what is left
- `apply_order(session, order_items)` — decrement, skipping untracked items
- `restore_order(session, order_items)` — re-increment the same way

Untracked items are skipped in both directions, so tracking can be switched on
and off at any time without corrupting a count.

### Categories

`update_category` and `delete_category` in `menu.py`, reusing the existing
`service.owned_restaurant` and `_category_in_restaurant` guards:

| Route | Behaviour |
| --- | --- |
| `PATCH /restaurants/{rid}/categories/{cid}` | `CategoryUpdate` (name, sort_order — both optional). Returns `CategoryResponse`. |
| `DELETE /restaurants/{rid}/categories/{cid}` | 204 when empty; `ConflictException` (409) when it still holds items; 404 when it belongs to another restaurant. |

### Checkout and the order lifecycle

- `checkout.py` gate 2 extends its existing `ITEM_OUT_OF_STOCK` check to reject
  a line whose quantity exceeds remaining stock. The same error code is reused,
  so the frontend needs no new handling.
- `create_order_from_checkout` calls `apply_order` inside the transaction it
  already opens, before `commit`.
- The four cancellation paths — `cancel_by_customer`, `reject_by_restaurant`,
  `advance_status` to CANCELLED, and `expire_pending_acceptances` — each call
  `restore_order`. `OrderItem.menu_item_id` carries no foreign key, so an item
  deleted after the order was placed is skipped rather than raising.

## Frontend

`OwnerPage.tsx` (500 lines) splits into `frontend/src/pages/owner/`, mirroring
the account split from phase D:

```
owner/
  OwnerPage.tsx      shell: restaurant selection + layout
  RestaurantForm.tsx create a restaurant
  IncomingOrders.tsx the orders panel
  MenuManager.tsx    loads the detail, open/closed toggle, cover image, add category
  CategoryPanel.tsx  one category: rename, delete, its items
  MenuItemPanel.tsx  one menu row: image, price, stock state, controls
  ItemForm.tsx       add / edit an item, including its stock
```

Two controls move into the shared kit rather than living in `owner/`, because
the customer pages need them too:

- `Thumb` — an image with a built-in placeholder, so a missing upload never
  leaves a broken box. Used by the restaurant cards, the detail hero, and both
  menus.
- `FilePicker` — the styled file input, previously repeated per upload site.

Customer-facing display, the half that is missing:

- Cover thumbnails on the browse cards and the detail hero; item thumbnails on
  the menu rows.
- Menu rows read `in_stock`: an out-of-stock row shows a badge and a disabled
  Add button. A tracked item at or below five remaining shows how many are
  left, which is the whole point of the feature for the customer.

## Test plan

Written test-first per the repository TDD convention.

| Test | Asserts |
| --- | --- |
| `tests/modules/restaurants/test_categories.py` | Rename changes the name; sort_order updates; deleting an empty category succeeds; deleting one with items 409s; another owner's category 404s; a non-owner is refused |
| `tests/modules/restaurants/test_inventory.py` | `in_stock` is false at zero stock and true when untracked; the checkout gate rejects a line above remaining stock; ordering decrements; untracked items are untouched |
| `tests/modules/orders/test_stock_restore.py` | Customer cancel, restaurant reject, admin cancel, and acceptance expiry each restore stock; a deleted menu item is skipped without raising |
| `frontend/tests/pages/owner/CategoryPanel.test.tsx` | Rename patches the category; an unchanged name sends nothing; cancel restores it; delete asks for confirmation first; a rejected delete surfaces the 409 message |
| `frontend/tests/pages/owner/ItemForm.test.tsx` | Blank stock sends null; a typed count sends the number; editing prefills; clearing sends null; **zero sends zero, not null** — sold out and untracked must not collapse |
| `frontend/tests/pages/RestaurantDetailPage.test.tsx` | Out of stock shows the badge and disables Add; a manually disabled item with stock left is also out of stock; a low count is announced and a healthy one is not; item and cover images render, and a missing one falls back |

## Verification

```bash
pytest                         # backend, must stay green
flake8 src                     # must stay clean
cd frontend && npm test        # vitest
cd frontend && npm run build   # tsc + vite
alembic upgrade head           # migration applies
```

## Out of scope

- Stock reservation while an item sits in a cart. Stock moves at order time;
  two customers can hold the last portion in their carts and the second one
  loses at checkout, with the existing `ITEM_OUT_OF_STOCK` message.
- Low-stock alerts or reorder points.
- Stock history or an audit trail of adjustments.
- Bulk import of a menu.
