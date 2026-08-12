import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi, FOOD_TYPE_LABELS } from '../../api/restaurants'
import type { AdminRestaurantRow, ApprovalStatus } from '../../api/restaurants'
import { Alert, Button, EmptyState, Loading, Modal } from '../../components/ui'

/**
 * The operator's restaurant list, and the only place approval is decided.
 *
 * Deliberately has no "add restaurant" control. Owners register their own
 * venue; an operator's job here is to decide whether a registered one trades,
 * and a restaurant created by an operator would have nobody to run it.
 */

const FILTERS: { key: ApprovalStatus | 'all'; label: string }[] = [
  // Pending first and selected by default: it is the queue, and the only tab
  // with work waiting on it.
  { key: 'pending', label: 'Pending' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'all', label: 'All' },
]

const STATUS_CLASS: Record<ApprovalStatus, string> = {
  pending: 'chip',
  approved: 'chip chip-accent',
  rejected: 'chip chip-danger',
}

export function RestaurantsPanel() {
  const [filter, setFilter] = useState<ApprovalStatus | 'all'>('pending')
  const [rows, setRows] = useState<AdminRestaurantRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  // Which decision is in flight, not merely which row. Keyed on the row alone,
  // approving a venue spun the spinner on its Reject button too.
  const [busy, setBusy] = useState<{ id: number; status: ApprovalStatus } | null>(null)
  // The venue being rejected, held while the reason is typed.
  const [rejecting, setRejecting] = useState<AdminRestaurantRow | null>(null)
  const [reason, setReason] = useState('')

  const load = useCallback(async () => {
    setError(null)
    try {
      const page = await restaurantsApi.adminList(filter === 'all' ? undefined : filter)
      setRows(page.items)
    } catch (e) {
      setError(errorMessage(e, 'Could not load restaurants.'))
      setRows([])
    }
  }, [filter])

  useEffect(() => {
    void load()
  }, [load])

  async function decide(row: AdminRestaurantRow, status: ApprovalStatus, why?: string) {
    setBusy({ id: row.id, status })
    setError(null)
    setNotice(null)
    try {
      await restaurantsApi.decideApproval(row.id, status as 'approved' | 'rejected', why)
      setNotice(`${row.name} ${status}.`)
      setRejecting(null)
      setReason('')
      await load()
    } catch (e) {
      setError(errorMessage(e, `Could not ${status.replace(/d$/, '')} this restaurant.`))
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <div className="admin-section-head">
        <h1>Restaurants</h1>
      </div>
      <p className="muted" style={{ marginTop: '-0.5rem' }}>
        Owners register their own restaurants. Approve or reject each registration — a venue
        stays invisible to customers until it is approved.
      </p>

      <div className="filter-row" style={{ margin: '1.25rem 0' }}>
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            className={`chip chip-btn ${filter === f.key ? 'chip-on' : ''}`}
            aria-pressed={filter === f.key}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && <Alert>{error}</Alert>}
      {notice && <Alert kind="ok">{notice}</Alert>}

      {rows === null ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState>
          {filter === 'pending'
            ? 'Nothing waiting for approval.'
            : `No ${filter === 'all' ? '' : filter} restaurants.`}
        </EmptyState>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Restaurant</th>
                <th>Owner</th>
                <th>City / address</th>
                <th>Contact</th>
                <th>Food type</th>
                <th>Open</th>
                <th>Approval</th>
                <th>Rating</th>
                <th>Reviews</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>{r.name}</strong>
                    {r.rejection_reason && (
                      <div className="muted" style={{ fontSize: '0.85em' }}>
                        {r.rejection_reason}
                      </div>
                    )}
                  </td>
                  {/* Empty when no user event has been seen for this owner yet.
                      The venue still lists — an operator needs to see it. */}
                  <td>{r.owner_name || <span className="muted">Unknown</span>}</td>
                  <td>
                    {r.city}
                    <div className="muted" style={{ fontSize: '0.85em' }}>{r.address_line}</div>
                  </td>
                  <td>{r.phone}</td>
                  <td>{FOOD_TYPE_LABELS[r.food_type]}</td>
                  <td>
                    <span className={`badge ${r.is_open ? 'badge-open' : 'badge-closed'}`}>
                      {r.is_open ? 'Open' : 'Closed'}
                    </span>
                  </td>
                  <td>
                    <span className={STATUS_CLASS[r.approval_status]}>{r.approval_status}</span>
                  </td>
                  {/* null, not 0 — an unrated restaurant is not a nought-star one. */}
                  <td>{r.rating_average === null ? <span className="muted">—</span> : r.rating_average.toFixed(1)}</td>
                  <td>{r.review_count}</td>
                  <td>
                    <div className="row-actions">
                      {r.approval_status !== 'approved' && (
                        <Button
                          variant="ghost"
                          loading={busy?.id === r.id && busy.status === 'approved'}
                          onClick={() => decide(r, 'approved')}
                        >
                          Approve
                        </Button>
                      )}
                      {/* Opens the reason modal rather than deciding, so it
                          never spins — only disabled while its row is busy. */}
                      {r.approval_status !== 'rejected' && (
                        <Button
                          variant="ghost"
                          disabled={busy?.id === r.id}
                          onClick={() => {
                            setRejecting(r)
                            setReason('')
                          }}
                        >
                          Reject
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* A reason is asked for rather than required: the owner is shown it, so a
          rejection without one leaves them nothing to act on — but an operator
          rejecting obvious spam should not have to justify it. */}
      <Modal
        open={rejecting !== null}
        title={`Reject ${rejecting?.name ?? ''}`}
        onClose={() => setRejecting(null)}
      >
        <label className="field">
          <span>Reason (shown to the owner)</span>
          <textarea
            className="input"
            rows={3}
            maxLength={500}
            value={reason}
            placeholder="e.g. Food licence not provided"
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        <div className="row-actions" style={{ marginTop: '1rem' }}>
          <Button
            loading={busy?.id === rejecting?.id && busy?.status === 'rejected'}
            onClick={() => rejecting && decide(rejecting, 'rejected', reason.trim() || undefined)}
          >
            Reject restaurant
          </Button>
          <Button variant="ghost" onClick={() => setRejecting(null)}>
            Cancel
          </Button>
        </div>
      </Modal>
    </>
  )
}
