import type { MenuItem } from '../../api/restaurants'
import { FilePicker, Thumb } from '../../components/ui'

interface MenuItemPanelProps {
  item: MenuItem
  onEdit: () => void
  onToggleAvailable: () => void
  onDelete: () => void
  onPickImage: (file: File) => void
}

/** One row of the owner's menu: image, price, stock state, and its controls. */
export function MenuItemPanel({
  item,
  onEdit,
  onToggleAvailable,
  onDelete,
  onPickImage,
}: MenuItemPanelProps) {
  return (
    <div className="menu-item">
      <div className="menu-item-lead">
        <Thumb url={item.image_url} alt={item.name} />
        <div>
          <div className="menu-item-name">
            {item.name}
            {!item.in_stock && <span className="badge badge-closed">Out of stock</span>}
          </div>
          <div className="muted">
            ${Number(item.price).toFixed(2)} · <StockLabel item={item} />
          </div>
        </div>
      </div>
      <div className="menu-item-actions">
        <FilePicker label="Photo" small onPick={onPickImage} />
        <button className="link-btn" onClick={onEdit}>Edit</button>
        <button className="link-danger" onClick={onToggleAvailable}>
          {item.is_available ? 'Mark unavailable' : 'Mark available'}
        </button>
        <button className="link-danger" onClick={onDelete} aria-label={`Delete ${item.name}`}>
          Delete
        </button>
      </div>
    </div>
  )
}

function StockLabel({ item }: { item: MenuItem }) {
  if (item.stock_quantity === null) return <>Stock not tracked</>
  return <>{item.stock_quantity} in stock</>
}
