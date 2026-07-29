// Shared helpers for presenting order status.

const LABELS: Record<string, string> = {
  CREATED: 'Created',
  PAYMENT_PENDING: 'Payment pending',
  PAYMENT_SUCCESS: 'Confirmed',
  RESTAURANT_ACCEPTED: 'Accepted',
  PREPARING: 'Preparing',
  READY_FOR_PICKUP: 'Ready for pickup',
  OUT_FOR_DELIVERY: 'Out for delivery',
  DELIVERED: 'Delivered',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  REJECTED: 'Rejected',
}

// States from which a customer may still cancel freely (pre-preparation).
const CUSTOMER_CANCELLABLE = new Set([
  'CREATED',
  'PAYMENT_PENDING',
  'PAYMENT_SUCCESS',
  'RESTAURANT_ACCEPTED',
])

export function statusLabel(status: string): string {
  return LABELS[status] ?? status
}

export function canCustomerCancel(status: string): boolean {
  return CUSTOMER_CANCELLABLE.has(status)
}
