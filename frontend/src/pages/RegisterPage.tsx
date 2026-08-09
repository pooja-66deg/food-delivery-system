import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'

import { authApi } from '../api/auth'
import type { SignupRole } from '../api/auth'
import { FOOD_TYPE_LABELS, FOOD_TYPES } from '../api/restaurants'
import type { FoodType } from '../api/restaurants'
import { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { BrandPanel } from '../components/BrandPanel'
import { Alert, Button, Field, PasswordField, PhoneField } from '../components/ui'
import { filterNameInput } from '../lib/inputFilters'
import { normalizePhone, PHONE_ERROR } from '../lib/phone'

export function RegisterPage() {
  const navigate = useNavigate()
  const { saveSession } = useAuth()

  const [role, setRole] = useState<SignupRole>('customer')
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    password: '',
  })
  const [venue, setVenue] = useState({
    name: '',
    city: '',
    address_line: '',
    phone: '',
    cuisine: '',
    food_type: 'both' as FoodType,
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Set only for a restaurant applicant, whose account is created inactive.
  // There is no session to send them to, so the form is replaced by an
  // explanation of what happens next — see handleSubmit.
  const [submitted, setSubmitted] = useState(false)

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const setFiltered =
    (key: keyof typeof form, filter: (v: string) => string) =>
    (e: { target: { value: string } }) =>
      setForm((f) => ({ ...f, [key]: filter(e.target.value) }))

  const setVenueField = (key: keyof typeof venue) => (e: { target: { value: string } }) =>
    setVenue((v) => ({ ...v, [key]: e.target.value }))

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    const phone = normalizePhone(form.phone)
    if (phone === null) {
      setError(PHONE_ERROR)
      return
    }
    const isRestaurant = role === 'restaurant'
    // The venue's own number is normalised separately: it is a different
    // business fact from the owner's personal phone and is stored on the
    // restaurant, not the account.
    let venuePhone: string | null = null
    if (isRestaurant) {
      venuePhone = normalizePhone(venue.phone)
      if (venuePhone === null) {
        setError(PHONE_ERROR)
        return
      }
    }
    setBusy(true)
    setError(null)
    void (async () => {
      try {
        await authApi.register({
          ...form,
          phone,
          role,
          ...(isRestaurant && venuePhone !== null
            ? {
                restaurant: {
                  name: venue.name,
                  city: venue.city,
                  address_line: venue.address_line,
                  phone: venuePhone,
                  // Empty optional fields are sent as null rather than "",
                  // which would store a blank cuisine as if it were a choice.
                  cuisine: venue.cuisine.trim() || null,
                  food_type: venue.food_type,
                },
              }
            : {}),
        })
        if (isRestaurant) {
          // No auto-login: the account is inactive until an operator approves
          // the venue, so logging in here would only produce the rejection the
          // applicant is about to be told about in plainer words.
          setSubmitted(true)
          return
        }
        const tokens = await authApi.login(form.email, form.password)
        await saveSession(tokens)
        // Send each role to its home screen.
        const home = role === 'driver' ? '/deliveries' : '/restaurants'
        navigate(home)
      } catch (err) {
        setError(errorMessage(err, 'Something went wrong.'))
      } finally {
        setBusy(false)
      }
    })()
  }

  if (submitted) {
    return (
      <div className="auth-split">
        <BrandPanel />
        <main className="auth-form-panel">
          <motion.div
            className="auth-card"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          >
            <h2>Registration received</h2>
            <p className="sub">
              Thanks — <strong>{venue.name}</strong> has been sent to our team for
              review.
            </p>
            <p className="sub">
              You won't be able to sign in just yet. Once your restaurant is
              approved we'll email <strong>{form.email}</strong>, and you can sign
              in and start building your menu straight away.
            </p>
            <p className="auth-foot">
              <Link to="/login">Back to sign in</Link>
            </p>
          </motion.div>
        </main>
      </div>
    )
  }

  return (
    <div className="auth-split">
      <BrandPanel />
      <main className="auth-form-panel">
        <motion.div
          className="auth-card"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        >
          <h2>Create your account</h2>
          <p className="sub">
            {role === 'restaurant'
              ? 'List your kitchen and start taking orders.'
              : role === 'driver'
                ? 'Sign up to pick up and deliver orders.'
                : 'A few details and your first order is minutes away.'}
          </p>

          <div className="tabs" style={{ marginBottom: '1.5rem' }}>
            <button type="button" className="tab" data-active={role === 'customer'} onClick={() => setRole('customer')}>
              Customer
            </button>
            <button type="button" className="tab" data-active={role === 'restaurant'} onClick={() => setRole('restaurant')}>
              Restaurant
            </button>
            <button type="button" className="tab" data-active={role === 'driver'} onClick={() => setRole('driver')}>
              Driver
            </button>
          </div>

          {error && <Alert>{error}</Alert>}

          <form className="form-stack" onSubmit={handleSubmit} style={{ marginTop: error ? '1rem' : 0 }}>
            <div className="form-row">
              <Field
                label="First name"
                name="first_name"
                autoComplete="given-name"
                placeholder="Alex"
                value={form.first_name}
                onChange={setFiltered('first_name', filterNameInput)}
                pattern="[A-Za-z ]+"
                title="Letters only"
                required
              />
              <Field
                label="Last name"
                name="last_name"
                autoComplete="family-name"
                placeholder="Rivera"
                value={form.last_name}
                onChange={setFiltered('last_name', filterNameInput)}
                pattern="[A-Za-z ]+"
                title="Letters only"
                required
              />
            </div>
            <Field
              label="Email"
              name="email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={form.email}
              onChange={set('email')}
              required
            />
            <PhoneField
              label="Phone"
              name="phone"
              value={form.phone}
              onChange={(phone) => setForm((f) => ({ ...f, phone }))}
              required
            />
            <PasswordField
              label="Password"
              name="password"
              autoComplete="new-password"
              placeholder="At least 8 characters"
              value={form.password}
              onChange={set('password')}
              minLength={8}
              required
            />
            {role === 'restaurant' && (
              <>
                <div className="form-section-head">
                  <h3>Your restaurant</h3>
                  <small className="muted">
                    An administrator reviews these before your listing goes live.
                  </small>
                </div>
                <Field
                  label="Restaurant name"
                  name="restaurant_name"
                  placeholder="Spice Garden"
                  value={venue.name}
                  onChange={setVenueField('name')}
                  maxLength={150}
                  required
                />
                <Field
                  label="Address"
                  name="restaurant_address"
                  placeholder="12 Residency Road"
                  value={venue.address_line}
                  onChange={setVenueField('address_line')}
                  maxLength={255}
                  required
                />
                <div className="form-row">
                  <Field
                    label="City"
                    name="restaurant_city"
                    placeholder="Bengaluru"
                    value={venue.city}
                    onChange={setVenueField('city')}
                    maxLength={100}
                    required
                  />
                  <Field
                    label="Cuisine"
                    name="restaurant_cuisine"
                    placeholder="North Indian"
                    value={venue.cuisine}
                    onChange={setVenueField('cuisine')}
                    maxLength={80}
                  />
                </div>
                <PhoneField
                  label="Restaurant phone"
                  name="restaurant_phone"
                  value={venue.phone}
                  onChange={(phone) => setVenue((v) => ({ ...v, phone }))}
                  required
                />
                {/* htmlFor/id rather than a wrapping label, matching Field: the
                    helper text below would otherwise be folded into the
                    control's accessible name. */}
                <div className="field">
                  <label htmlFor="signup_food_type">Food type</label>
                  <select
                    id="signup_food_type"
                    className="input"
                    name="food_type"
                    value={venue.food_type}
                    onChange={(e) =>
                      setVenue((v) => ({ ...v, food_type: e.target.value as FoodType }))
                    }
                  >
                    {FOOD_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {FOOD_TYPE_LABELS[t]}
                      </option>
                    ))}
                  </select>
                  <small className="muted">
                    Customers filtering for vegetarian see only restaurants set to
                    “Vegetarian”.
                  </small>
                </div>
              </>
            )}
            <Button type="submit" block loading={busy}>
              {role === 'restaurant' ? 'Submit for approval' : 'Create account'}
            </Button>
          </form>

          <p className="auth-foot">
            Already have an account? <Link to="/login">Sign in</Link>
          </p>
        </motion.div>
      </main>
    </div>
  )
}
