# Restaurant Management Dashboard Redesign (3-Column Layout)

**Date:** 2026-08-05  
**Status:** Design Spec  
**Objective:** Redesign `/manage` (OwnerPage) to use full viewport space with improved visual hierarchy and eliminate excessive whitespace using a 3-column layout.

---

## Problem Statement

The current OwnerPage uses a 2-column layout (narrow left sidebar + wide right panel) that:
- Stacks IncomingOrders and MenuManager vertically, making it hard to manage both simultaneously
- Leaves significant whitespace, especially on wide screens
- Forces scrolling to see orders and menu items together
- Lacks visual polish and clear component hierarchy

**Target:** Enable restaurant owners to view and manage restaurants, incoming orders, and menu inventory in a single cohesive view with clear visual separation and proper space utilization.

---

## Layout Architecture

### Grid Structure
```
┌─────────────────────────────────────────────────────────┐
│ Header: "Manage your restaurants"                        │
└─────────────────────────────────────────────────────────┘

┌──────────────┬──────────────────┬─────────────────────┐
│  SIDEBAR     │   CENTER         │      RIGHT          │
│  Restaurants │ Incoming Orders  │  Menu Manager       │
│   (280px)    │     (~32%)        │   (remaining)       │
└──────────────┴──────────────────┴─────────────────────┘
```

**Column Configuration:**
- **Left:** Fixed 280px (restaurant sidebar)
- **Center:** ~32% of remaining space (orders panel)
- **Right:** Remaining space (menu panel)
- **Gap:** 1.5rem between columns
- **Breakpoint:** Stacks to 2-column at <1000px, single column at <780px

---

## Component Specifications

### 1. Left Sidebar: Restaurants Panel

**Structure:**
```
┌─ Restaurants Panel ────────────────┐
│ h2: "Your restaurants"             │
├────────────────────────────────────┤
│ [Restaurant Card 1] (active)       │
│ [Restaurant Card 2]                │
│ [Restaurant Card 3]                │
├────────────────────────────────────┤
│ [Create Restaurant Form]           │
└────────────────────────────────────┘
```

**Restaurant Card Changes:**
- Padding: 0.9rem (from 0.7rem) for better breathing room
- Border: 1px solid var(--line), radius var(--r-sm)
- Flex layout: name (flex: 1) + status badge (right-aligned)
- **Active state:** border-color tomato, background subtle highlight, box-shadow
- Hover state: background lightens slightly, cursor pointer
- Typography: name in 600 weight, badge in 500 weight

**Create Restaurant Form:**
- Displayed at bottom of sidebar
- Border-top: 1px solid var(--line)
- Padding-top: 1rem
- Flex column layout with gap 0.75rem
- Full-width button ("Create restaurant")

**Visual Polish:**
- Section heading margin-bottom: 1.1rem
- Cards have consistent 0.5rem gap between them
- Form has clear visual separation from list

---

### 2. Center Panel: Incoming Orders

**Structure:**
```
┌─ Incoming Orders ──────────────────┐
│ [Header: h2 + Refresh Button]      │
├────────────────────────────────────┤
│ [Order Card 1]                     │
│ [Order Card 2]                     │
│ [Order Card 3]                     │
└────────────────────────────────────┘
```

**Order Card Design:**
- **Header row:** 
  - Order ID (bold, #XXXXXX)
  - Time (muted, small)
  - Total price (bold, right-aligned)
- **Items row:**
  - Item list (compact, max 2 lines, "Item × Qty" format)
  - Truncate if overflow
- **Footer row:**
  - Status badge (left)
  - Action buttons (Accept/Decline/Ready/Mark Complete - right-aligned)
- Padding: 1rem
- Border: 1px solid var(--line)
- Border-radius: var(--r-md)
- Background: rgba(255,255,255, 0.5)
- Margin-bottom: 0.75rem
- Hover: box-shadow lightens, slight background change

**Header Styling:**
- Flex row: h2 (flex: 1) + Refresh button (right)
- Margin-bottom: 1rem
- Button variant: "ghost" with icon or text

**Empty State:**
- Show only when no orders
- Centered text: "No incoming orders"

**Visual Polish:**
- Consistent spacing and alignment
- Clear visual hierarchy: ID > Items > Actions
- Status badges with appropriate colors (pending=amber, accepted=green, etc.)

---

### 3. Right Panel: Menu Manager

**Structure:**
```
┌─ Menu Manager ─────────────────────┐
│ [Header: Restaurant name + Toggle] │
├────────────────────────────────────┤
│ [Cover Image]                      │
│ [Upload Button]                    │
├────────────────────────────────────┤
│ [Delivery Zone Panel]              │
├────────────────────────────────────┤
│ [Add Category Form]                │
├────────────────────────────────────┤
│ Category 1                         │
│ ├─ [Item Card] [Item Card]         │
│ ├─ [Item Card] [Item Card]         │
│ Category 2                         │
│ ├─ [Item Card] [Item Card]         │
│ ├─ [Item Card] [Item Card]         │
└────────────────────────────────────┘
```

**Header Section:**
- Flex row: h2 restaurant name (flex: 1) + "Set open/closed" button
- Margin-bottom: 1.25rem
- Button variant: "ghost"

**Cover Image Section:**
- Full-width image with aspect ratio (16:9 or similar)
- Height: ~150px
- Border-radius: var(--r-md)
- Margin-bottom: 1rem
- FilePicker below with label

**Delivery Zone Panel:**
- Compact form section
- Margin-bottom: 1rem

**Add Category Form:**
- Flex row: input (flex: 1) + button
- Flex-wrap: wrap for small screens
- Gap: 0.6rem
- Margin: 0.75rem 0 1rem

**Menu Grid (New):**
- **Change from stacked list to 2-column grid**
- Display: grid
- Grid-template-columns: repeat(auto-fill, minmax(180px, 1fr))
- Gap: 0.75rem
- Each category gets its own grid

**Item Card Design (New Component):**
- Padding: 0.75rem
- Border: 1px solid var(--line)
- Border-radius: var(--r-sm)
- Background: var(--paper)
- **Layout:**
  - Image (full-width, height 100px, object-fit: cover)
  - Name (bold, 0.9rem, max 2 lines, truncate)
  - Price (bold, color accent)
  - Availability toggle (checkbox or switch)
  - Action buttons (Edit icon, Delete icon) in footer
- Hover: border-color change, shadow, slight scale

**Category Header:**
- h3 with border-bottom and padding-bottom: 0.75rem
- Margin-top: 1.5rem (first), 1.5rem (subsequent)
- Margin-bottom: 0.75rem

**Visual Polish:**
- Consistent padding and margins throughout
- Clear section separations with borders/spacing
- Icons for actions (edit, delete) instead of text buttons
- Availability toggle is intuitive (checkbox or switch)
- Hover states on all interactive elements

---

## Color & Typography

**Typography Changes:**
- Section headers (h2): margin-bottom 1.1rem, font-size 1.1rem, weight 700
- Category headers (h3): font-size 1rem, weight 600
- Card titles: weight 600, size 0.95rem
- Prices: weight 700, color accent (tomato/brand color)
- Muted text: color var(--muted), font-size 0.85rem

**Spacing Improvements:**
- Card padding: 0.75rem-1rem (from tight spacing)
- List gaps: 0.5-0.75rem (from inconsistent)
- Section margins: 1.5rem vertical (from mixed)
- Horizontal padding in panels: 1.25rem

**Badges & Buttons:**
- Status badges: proper padding, rounded, colored backgrounds
- Action buttons: icon-only for compact space, proper hit targets (44px minimum)
- Primary button (create/add): full-width in forms
- Secondary buttons (ghost variant): minimal visual weight

---

## Responsive Design

### Breakpoint 1: Wide Screens (1400px+)
- 3-column layout as specified
- Menu grid: 2-3 columns
- All sections visible simultaneously

### Breakpoint 2: Medium Screens (1000-1400px)
- Switch to 2-column:
  - Left: Restaurants sidebar (280px)
  - Right: Orders + Menu stacked (with explicit divider/spacing)
- Menu grid: 2 columns
- Orders and menu panels have equal height constraints or scrollable regions

### Breakpoint 3: Small Screens (<1000px)
- Single column stack (existing mobile behavior)
- Restaurants sidebar collapses to dropdown/tabs
- Orders and Menu stack vertically

---

## Implementation Details

### Files to Modify
1. **frontend/src/pages/owner/OwnerPage.tsx**
   - Change layout from 2-column to 3-column grid
   - Update className structure

2. **frontend/src/layout.css**
   - Update .owner-grid to new 3-column template
   - Add new .order-card styles
   - Add new .menu-item-card styles for grid layout
   - Update .owner-panel sizing/spacing
   - Add responsive breakpoint adjustments

3. **frontend/src/pages/owner/IncomingOrders.tsx** (minor)
   - Ensure order cards follow new design
   - OrderOps component styling

4. **frontend/src/pages/owner/MenuManager.tsx** (minor)
   - No component structure changes, styling via CSS
   - Menu items displayed via grid instead of list

5. **frontend/src/pages/owner/CategoryPanel.tsx** (minor)
   - Update to render items in grid format
   - Existing logic unchanged

### CSS Changes Summary
- `.owner-grid`: Update to `grid-template-columns: 280px 1fr 1fr` (adjust right column)
- New `.order-card`: Card styling for orders
- New `.menu-item-card`: Card styling for menu items in grid
- New `.menu-grid`: Grid container for items
- Update `.owner-panel`: Padding/borders for better visual hierarchy
- Update responsive rules for medium/small screens

### No Component Logic Changes
- All API calls, state management, and functionality remain unchanged
- Pure CSS/layout restructuring
- Visual enhancements only (spacing, cards, grid)

---

## Success Criteria

✓ All three sections (Restaurants, Orders, Menu) visible simultaneously on wide screens  
✓ Menu items displayed in grid format (2+ columns) instead of stacked list  
✓ Visual hierarchy clear through spacing, colors, and typography  
✓ No excessive whitespace; content properly distributed  
✓ Cards have proper padding and breathing room  
✓ Responsive behavior at medium/small breakpoints  
✓ No functionality loss or behavior changes  
✓ Existing restaurant/order/menu operations work identically  

---

## Testing Plan

1. **Visual Testing:**
   - Open /manage on wide screen (1400px+) - verify 3-column layout
   - Verify menu items show in 2-column grid
   - Check all cards have proper spacing and styling
   - Verify no whitespace issues

2. **Responsive Testing:**
   - Resize to 1200px - verify layout adjusts
   - Resize to 900px - verify stacks properly
   - Test on mobile - verify single column works

3. **Functional Testing:**
   - Create restaurant - still works
   - Select restaurant - orders/menu load
   - Accept order - order card updates
   - Edit menu item - form opens correctly
   - Upload images - displays properly
   - All existing features work unchanged

4. **Accessibility:**
   - Keyboard navigation works
   - Screen reader announces sections properly
   - Color contrast meets WCAG AA

---

## Open Questions / Decisions

- **Menu grid columns:** Fixed 2-column or auto-fit with minmax?  
  → Recommendation: auto-fill, minmax(180px, 1fr) for flexibility
  
- **Order card actions:** Keep existing buttons or replace with icon buttons?  
  → Recommendation: Keep existing buttons but ensure proper spacing

- **Color scheme:** Maintain current var(--tomato) for accent or adjust?  
  → Recommendation: Keep current scheme, just improve spacing/hierarchy

---

## Related Files
- `frontend/src/pages/owner/OwnerPage.tsx` - Main component
- `frontend/src/pages/owner/IncomingOrders.tsx` - Orders panel
- `frontend/src/pages/owner/MenuManager.tsx` - Menu panel
- `frontend/src/layout.css` - Styling to update
