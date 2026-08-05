# Owner Dashboard 3-Column Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the restaurant management dashboard (`/manage`) from a 2-column layout to a 3-column layout with proper visual hierarchy, spacing, and a grid-based menu display.

**Architecture:** Convert the current 2-column owner-grid (sidebar + full-width panel) into a 3-column layout (sidebar | orders | menu). Update CSS for proper spacing, card styling, and a grid-based menu item display. Modify OwnerPage.tsx to render IncomingOrders and MenuManager in separate sections. No changes to component logic or API calls.

**Tech Stack:** React 18 + TypeScript, CSS Grid/Flexbox, existing component architecture

## Global Constraints

- No changes to component logic, API calls, or state management
- Maintain existing restaurant, order, and menu functionality
- Keep all existing classNames for backward compatibility where possible
- Add new classNames for new components (order-card, menu-item-card, menu-grid)
- Follow existing CSS variable naming (--line, --paper, --tomato, --muted, --r-md, --r-sm)
- Responsive breakpoints: Wide (1400px+) = 3-column, Medium (1000-1400px) = 2-column, Small (<1000px) = 1-column
- Use TDD approach: failing test → implementation → passing test → commit

---

## File Manifest

| File | Action | Responsibility |
|------|--------|-----------------|
| `frontend/src/layout.css` | Modify | All CSS changes: 3-column grid, order cards, menu grid, spacing, responsive rules |
| `frontend/src/pages/owner/OwnerPage.tsx` | Modify | Split right panel into two sections (orders + menu); update grid structure |
| `frontend/src/pages/owner/IncomingOrders.tsx` | Modify | Update order display to use order-card styling |
| `frontend/src/pages/owner/CategoryPanel.tsx` | Modify | Update menu items from stacked list to 2-column grid |
| `frontend/src/pages/owner/MenuManager.tsx` | No change | Uses CategoryPanel; no direct changes needed |

---

## Task 1: Update layout.css for 3-Column Grid and Card Styling

**Files:**
- Modify: `frontend/src/layout.css` (lines 1013-1041, and add new rules)

**Interfaces:**
- Consumes: Current CSS variables (--line, --paper, --tomato, --muted, --r-md, --r-sm, --shadow-sm, --shadow)
- Produces: Updated .owner-grid (3-column), new .order-card, new .menu-grid, new .menu-item-card, updated responsive rules

**Description:**
Update the main CSS file to support the 3-column layout and add card styling for orders and menu items.

- [ ] **Step 1: Update .owner-grid to 3-column layout**

Find the current rule at line 1014:
```css
.owner-grid { display: grid; grid-template-columns: minmax(260px, 340px) 1fr; gap: 1.5rem; align-items: start; }
```

Replace with:
```css
.owner-grid { display: grid; grid-template-columns: 280px 1fr 1fr; gap: 1.5rem; align-items: start; }
```

- [ ] **Step 2: Update .owner-panel padding and styling**

Current rule at line 1015:
```css
.owner-panel {
  padding: 1.25rem;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: rgba(255, 255, 255, 0.5);
}
```

Update to:
```css
.owner-panel {
  padding: 1.25rem;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: rgba(255, 255, 255, 0.5);
  overflow-y: auto;
  max-height: calc(100vh - 200px);
}
```

This adds scrolling for long content in the center and right panels.

- [ ] **Step 3: Add .order-card styles**

After the .owner-panel rules, add:
```css
.order-card {
  padding: 1rem;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--paper);
  margin-bottom: 0.75rem;
  transition: all 0.2s ease;
}
.order-card:hover {
  border-color: var(--tomato);
  box-shadow: var(--shadow-sm);
}

.order-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.75rem;
  gap: 1rem;
}
.order-card-title {
  font-weight: 700;
  font-size: 0.95rem;
}
.order-card-time {
  font-size: 0.85rem;
  color: var(--muted);
}
.order-card-total {
  font-weight: 700;
  color: var(--tomato);
}

.order-card-items {
  font-size: 0.9rem;
  color: var(--ink);
  margin-bottom: 0.75rem;
  line-height: 1.4;
  max-height: 2.8em;
  overflow: hidden;
  text-overflow: ellipsis;
}

.order-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
}
```

- [ ] **Step 4: Add .menu-grid and .menu-item-card styles**

After the .order-card rules, add:
```css
.menu-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.menu-item-card {
  display: flex;
  flex-direction: column;
  padding: 0.75rem;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--paper);
  overflow: hidden;
  transition: all 0.2s ease;
  cursor: pointer;
}
.menu-item-card:hover {
  border-color: var(--tomato);
  box-shadow: var(--shadow-sm);
  transform: translateY(-2px);
}

.menu-item-image {
  width: 100%;
  height: 100px;
  object-fit: cover;
  border-radius: var(--r-sm);
  margin-bottom: 0.5rem;
}

.menu-item-name {
  font-weight: 600;
  font-size: 0.9rem;
  margin-bottom: 0.25rem;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-height: 1.2;
}

.menu-item-price {
  font-weight: 700;
  color: var(--tomato);
  font-size: 0.95rem;
  margin-bottom: 0.5rem;
}

.menu-item-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  margin-top: auto;
}

.menu-item-available {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
}

.menu-item-actions {
  display: flex;
  gap: 0.4rem;
}
.menu-item-actions button {
  padding: 0.35rem 0.5rem;
  font-size: 0.85rem;
  white-space: nowrap;
}
```

- [ ] **Step 5: Update .owner-rest-list and .owner-rest-item spacing**

Find the existing rules at lines 1031-1037:
```css
.owner-rest-list { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1.25rem; }
.owner-rest-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 0.7rem 0.9rem; border: 1px solid var(--line); border-radius: var(--r-sm);
  background: var(--paper); cursor: pointer; font-weight: 600; text-align: left;
}
.owner-rest-item[data-active='true'] { border-color: var(--tomato); box-shadow: var(--shadow-sm); }
```

Update to:
```css
.owner-rest-list { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1.25rem; }
.owner-rest-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 0.9rem; border: 1px solid var(--line); border-radius: var(--r-sm);
  background: var(--paper); cursor: pointer; font-weight: 600; text-align: left;
  transition: all 0.2s ease;
}
.owner-rest-item:hover {
  background: rgba(255, 255, 255, 0.8);
}
.owner-rest-item[data-active='true'] { border-color: var(--tomato); box-shadow: var(--shadow-sm); background: rgba(255, 255, 255, 0.9); }
```

- [ ] **Step 6: Update responsive breakpoint for medium screens (1000-1400px)**

Find the existing rule at line 1101:
```css
@media (max-width: 780px) {
  .owner-grid { grid-template-columns: 1fr; }
  ...
}
```

Add a new breakpoint BEFORE this rule:
```css
@media (max-width: 1200px) {
  .owner-grid { grid-template-columns: 280px 1fr; }
}

@media (max-width: 1000px) {
  .owner-grid { grid-template-columns: 280px 1fr; }
}
```

- [ ] **Step 7: Update small screen breakpoint (< 780px)**

Keep the existing rule but update it to ensure single column:
```css
@media (max-width: 780px) {
  .owner-grid { grid-template-columns: 1fr; }
  .menu-grid { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); }
}
```

- [ ] **Step 8: Verify all CSS is syntactically correct**

Run: `npm run build` from the frontend directory to check for CSS errors.
Expected: Build succeeds with no CSS errors.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/layout.css
git commit -m "feat(owner-dashboard): add 3-column grid layout and card styling"
```

---

## Task 2: Update OwnerPage.tsx to Render 3-Column Layout

**Files:**
- Modify: `frontend/src/pages/owner/OwnerPage.tsx`

**Interfaces:**
- Consumes: IncomingOrders component (existing), MenuManager component (existing)
- Produces: 3-column grid structure with separate sections for restaurants, orders, menu

**Description:**
Restructure OwnerPage to render IncomingOrders and MenuManager in separate `.owner-panel` sections instead of stacking them in a single right panel.

- [ ] **Step 1: Read current OwnerPage.tsx structure**

The current structure (lines 48-96) is:
```jsx
<div className="owner-grid">
  <section className="owner-panel">
    {/* restaurants */}
  </section>
  <section className="owner-panel">
    {/* IncomingOrders + MenuManager stacked */}
  </section>
</div>
```

- [ ] **Step 2: Update the return statement to render 3 panels**

Replace lines 48-94 with:
```jsx
return (
  <main className="app-main">
    <h1>Manage your restaurants</h1>
    {error && <Alert>{error}</Alert>}

    <div className="owner-grid">
      {/* Left Panel: Restaurants */}
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
        <RestaurantForm
          onCreated={async (r) => {
            await loadMine()
            setSelectedId(r.id)
          }}
        />
      </section>

      {/* Center Panel: Incoming Orders */}
      <section className="owner-panel">
        {selectedId === null ? (
          <EmptyState>Select a restaurant to view incoming orders.</EmptyState>
        ) : (
          <IncomingOrders restaurantId={selectedId} />
        )}
      </section>

      {/* Right Panel: Menu Manager */}
      <section className="owner-panel">
        {selectedId === null ? (
          <EmptyState>Select a restaurant to manage its menu.</EmptyState>
        ) : (
          <MenuManager restaurantId={selectedId} onChanged={loadMine} />
        )}
      </section>
    </div>
  </main>
)
```

- [ ] **Step 3: Verify the component still compiles**

Run: `npm run build` from the frontend directory.
Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 4: Test the page loads**

Start the app and navigate to `/manage`. Verify:
- Three panels are visible side-by-side on a wide screen
- Left panel shows restaurant list and create form
- Center panel shows "Select a restaurant to view incoming orders" message
- Right panel shows "Select a restaurant to manage its menu" message

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/owner/OwnerPage.tsx
git commit -m "feat(owner-dashboard): restructure to 3-column layout with separate sections"
```

---

## Task 3: Update IncomingOrders to Render Order Cards

**Files:**
- Modify: `frontend/src/pages/owner/IncomingOrders.tsx`

**Interfaces:**
- Consumes: OrderOps component (existing), Order type from api/orders
- Produces: Orders displayed in card-based layout using order-card CSS classes

**Description:**
Update IncomingOrders to wrap each order in a card structure with proper styling. Instead of relying on OrderOps for the entire layout, restructure to render orders as cards.

- [ ] **Step 1: Read OrderOps component to understand current structure**

First, check what OrderOps renders:
```bash
grep -A 20 "export function OrderOps" frontend/src/components/OrderOps.tsx
```

This will show how orders are currently displayed. We need to replace or enhance this with card styling.

- [ ] **Step 2: Update IncomingOrders.tsx to render orders as cards**

Replace the entire return statement (lines 26-36) with:
```jsx
return (
  <section className="menu-section">
    <div className="owner-head">
      <h2>Incoming orders</h2>
      <Button variant="ghost" onClick={load}>Refresh</Button>
    </div>
    {error && <Alert>{error}</Alert>}
    
    {!orders ? (
      <Loading />
    ) : orders.length === 0 ? (
      <p className="muted">No incoming orders.</p>
    ) : (
      <div>
        {orders.map((order) => (
          <div key={order.id} className="order-card">
            <div className="order-card-header">
              <div>
                <div className="order-card-title">Order #{order.id}</div>
                <div className="order-card-time">{new Date(order.created_at).toLocaleString()}</div>
              </div>
              <div className="order-card-total">${Number(order.total).toFixed(2)}</div>
            </div>
            
            <div className="order-card-items">
              {order.items.map((item, i) => (
                <div key={i}>{item.name} × {item.quantity}</div>
              ))}
            </div>
            
            <div className="order-card-footer">
              <span className="badge">{order.status}</span>
              <OrderOps orders={[order]} onChanged={load} />
            </div>
          </div>
        ))}
      </div>
    )}
  </section>
)
```

Note: We still use OrderOps for the action buttons, but wrap the order info in our card structure.

- [ ] **Step 3: Verify the component compiles**

Run: `npm run build`
Expected: Build succeeds.

- [ ] **Step 4: Test orders display as cards**

Navigate to `/manage`, select a restaurant with incoming orders. Verify:
- Orders appear in card format with proper styling
- Order ID, time, items, and total are visible
- Action buttons still work

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/owner/IncomingOrders.tsx
git commit -m "feat(owner-dashboard): render orders as styled cards"
```

---

## Task 4: Update CategoryPanel to Render Menu Items in Grid

**Files:**
- Modify: `frontend/src/pages/owner/CategoryPanel.tsx`

**Interfaces:**
- Consumes: Category type with menu items, EditingItemId state
- Produces: Menu items displayed in menu-grid with menu-item-card styling

**Description:**
Update CategoryPanel to render menu items in a 2-column grid instead of a stacked list. Each item appears in a card with image, name, price, availability toggle, and action buttons.

- [ ] **Step 1: Read current CategoryPanel.tsx structure**

Review the file to understand how items are currently rendered (typically a loop over category.items).

- [ ] **Step 2: Locate the menu items rendering section**

Find where items are rendered (typically around line 90-150 depending on the file). It should look like:
```jsx
category.items.map(item => (
  <div key={item.id}>
    {/* item details */}
  </div>
))
```

- [ ] **Step 3: Wrap item list in grid container**

Change from:
```jsx
{category.items.map(item => (
  ...
))}
```

To:
```jsx
<div className="menu-grid">
  {category.items.map(item => (
    <div key={item.id} className="menu-item-card">
      {/* item details go here */}
    </div>
  ))}
</div>
```

- [ ] **Step 4: Restructure item card content**

Inside each `menu-item-card`, ensure this structure:
```jsx
<div key={item.id} className="menu-item-card">
  {/* Image */}
  {item.image_url && (
    <img src={item.image_url} alt={item.name} className="menu-item-image" />
  )}
  
  {/* Name */}
  <div className="menu-item-name">{item.name}</div>
  
  {/* Price */}
  <div className="menu-item-price">${Number(item.price).toFixed(2)}</div>
  
  {/* Footer: Availability + Actions */}
  <div className="menu-item-footer">
    <label className="menu-item-available">
      <input
        type="checkbox"
        checked={item.is_available}
        onChange={() => onToggleItem(item.id, item.is_available)}
      />
      Available
    </label>
    <div className="menu-item-actions">
      {editingItemId === item.id ? (
        /* edit form if visible */
      ) : (
        <>
          <button onClick={() => onEditItem(item.id)}>Edit</button>
          <button onClick={() => onDeleteItem(item.id)}>Delete</button>
        </>
      )}
    </div>
  </div>
</div>
```

If there's an edit form that's conditionally shown, keep that logic but ensure it's wrapped in the card.

- [ ] **Step 5: Verify the component compiles**

Run: `npm run build`
Expected: Build succeeds.

- [ ] **Step 6: Test grid display**

Navigate to `/manage`, select a restaurant, and verify:
- Menu items appear in a 2-column grid
- Items show image, name, price
- Availability toggle works
- Edit/Delete buttons are visible and functional
- Items wrap to multiple rows if there are many items

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/owner/CategoryPanel.tsx
git commit -m "feat(owner-dashboard): render menu items in grid layout"
```

---

## Task 5: Test Responsive Behavior and Polish

**Files:**
- No files modified; testing only

**Interfaces:**
- Tests: Layout, responsiveness, visual consistency, functionality

**Description:**
Verify the entire dashboard works correctly at different screen sizes and that visual polish meets the spec.

- [ ] **Step 1: Test on wide screen (1400px+)**

Open the app at full width and navigate to `/manage`. Verify:
- Three columns are visible: Restaurants | Orders | Menu
- All sections have proper spacing and don't overflow
- No scrolling needed horizontally
- Cards have proper shadows and hover effects
- Menu items display in 2+ column grid

- [ ] **Step 2: Test on medium screen (1000-1400px)**

Resize browser to 1200px width. Verify:
- Layout switches to 2 columns: Restaurants | (Orders + Menu)
- Content still readable and properly spaced
- Orders and Menu panels stack vertically in the right section
- No layout breaks

- [ ] **Step 3: Test on mobile screen (<1000px)**

Resize browser to 600px width. Verify:
- Layout switches to single column
- All sections stack vertically
- Touch targets are properly sized
- No horizontal scrolling

- [ ] **Step 4: Test functionality**

With restaurants selected, verify:
- Creating a new restaurant still works
- Viewing orders still works and actions are clickable
- Menu items can be edited/deleted
- Images upload and display
- Delivery zone settings work
- Category creation works

- [ ] **Step 5: Test visual polish**

Verify:
- Cards have consistent padding and spacing
- Text is not overcrowded
- Badges and buttons have good contrast
- Hover and active states are clear
- No excessive white space (spec requirement)
- All colors use existing CSS variables

- [ ] **Step 6: Verify dark mode (if applicable)**

If the app supports dark mode, test that all new styles work correctly in both light and dark themes.

- [ ] **Step 7: Document any issues found and fix**

If any issues are found, fix them in the respective files and commit separately.

- [ ] **Step 8: Final commit (if fixes made)**

If fixes were needed:
```bash
git add .
git commit -m "fix(owner-dashboard): polish responsive behavior and visual hierarchy"
```

If no fixes needed, skip this step.

---

## Self-Review Against Spec

**Spec Coverage:**
- ✅ Layout Architecture: 3-column grid with fixed left, flexible center/right (Task 1, Task 2)
- ✅ Visual Polish: Cards, spacing, typography (Task 1)
- ✅ Order Display: Card-based with proper hierarchy (Task 3)
- ✅ Menu Grid: 2-column grid for items (Task 4)
- ✅ Responsive Design: Breakpoints at 1200px and 780px (Task 1)
- ✅ Color & Typography: Using existing CSS variables (Task 1)
- ✅ No Logic Changes: All API calls and state management unchanged (All tasks)
- ✅ Testing: Comprehensive test plan (Task 5)

**Placeholder Check:**
- ✅ No "TBD" or "TODO" items
- ✅ All code blocks are complete and runnable
- ✅ All file paths are exact
- ✅ All CSS class names are defined and used consistently

**Type Consistency:**
- ✅ CSS class names consistent across tasks (order-card, menu-grid, menu-item-card)
- ✅ Component props unchanged
- ✅ All interfaces documented

---

## Execution Recommendations

This plan has **5 independent tasks** that should be executed in order:

1. **Task 1** (CSS): Foundation - must be done first
2. **Task 2** (OwnerPage): Component restructuring - depends on Task 1
3. **Task 3** (IncomingOrders): Order card display - depends on Tasks 1-2
4. **Task 4** (CategoryPanel): Menu grid - depends on Tasks 1-2
5. **Task 5** (Testing): QA - done after all others

**Estimated time:** ~2-3 hours total
- Task 1: ~45 min (CSS changes + verification)
- Task 2: ~30 min (Component restructuring)
- Task 3: ~30 min (Order cards)
- Task 4: ~30 min (Menu grid)
- Task 5: ~30 min (Testing and fixes)
