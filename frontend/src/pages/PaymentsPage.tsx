import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { errorMessage } from '../api/client'
import { paymentsApi } from '../api/payments'
import type { Payment } from '../api/payments'
import { Alert, Button, EmptyState, Loading } from '../components/ui'

export function PaymentsPage() {
  const [items, setItems] = useState<Payment[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState<number | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setItems(await paymentsApi.history())
    } catch (e) {
      setError(errorMessage(e, 'Failed to load payments.'))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function retry(orderId: number) {
    setRetrying(orderId)
    try {
      await paymentsApi.retry(orderId)
      await load()
    } catch (e) {
      setError(errorMessage(e, 'Retry failed.'))
    } finally {
      setRetrying(null)
    }
  }

  return (
    <main className="app-main">
      <h1>Payments</h1>
      {error && <Alert>{error}</Alert>}
      {!items ? (
        <Loading />
      ) : items.length === 0 ? (
        <EmptyState>No payments yet.</EmptyState>
      ) : (
        <div className="admin-table" role="table">
          <div className="admin-row pay-row admin-head-row" role="row">
            <span>Order</span><span>Provider</span><span>Amount</span><span>Status</span><span></span>
          </div>
          {items.map((p) => (
            <div key={p.id} className="admin-row pay-row" role="row">
              <Link to={`/orders/${p.order_id}`} className="mono">#{p.order_id}</Link>
              <span className="muted">{p.provider}</span>
              <span className="price">${Number(p.amount).toFixed(2)}</span>
              <span><span className="chip">{p.status}</span></span>
              <span>
                {p.status === 'FAILED' && (
                  <Button variant="ghost" loading={retrying === p.order_id} onClick={() => retry(p.order_id)}>
                    Retry
                  </Button>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </main>
  )
}
