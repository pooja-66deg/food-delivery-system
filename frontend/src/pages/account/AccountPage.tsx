import { motion } from 'framer-motion'

import { useAuth } from '../../auth/AuthContext'
import { AddressPanel } from './AddressPanel'
import { NotificationPanel } from './NotificationPanel'
import { ProfilePanel } from './ProfilePanel'
import { SecurityPanel } from './SecurityPanel'
import { VerificationNotice } from './VerificationNotice'

const ROLE_LABELS: Record<string, string> = {
  customer: 'Customer account',
  restaurant: 'Restaurant account',
  driver: 'Driver account',
  admin: 'Admin account',
}

export function AccountPage() {
  const { user } = useAuth()
  // Delivery addresses are a customer concern — drivers and owners have no use
  // for them. Gating lives here so the panels stay unaware of roles.
  const isCustomer = user?.role === 'customer'

  return (
    <main className="app-main">
      <motion.div
        className="page-head"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
      >
        <span className="chip chip-accent">{ROLE_LABELS[user?.role ?? ''] ?? 'Account'}</span>
        <h1 style={{ marginTop: '0.6rem' }}>
          Hello, {user?.first_name} {user?.last_name}
        </h1>
        <p>
          Signed in as <strong>{user?.role}</strong>.{' '}
          {isCustomer ? 'Manage your profile details and delivery addresses.' : 'Manage your profile details.'}
        </p>
      </motion.div>

      <VerificationNotice />

      <div className="account-grid">
        <ProfilePanel />
        <SecurityPanel />
        <NotificationPanel />
        {isCustomer && <AddressPanel />}
      </div>
    </main>
  )
}
