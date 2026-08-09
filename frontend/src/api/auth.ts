// Typed bindings for the users/auth backend endpoints.

import { request } from './client'
import type { FoodType } from './restaurants'

export interface User {
  id: number
  email: string
  phone: string
  first_name: string
  last_name: string
  role: string
  is_active: boolean
  created_at: string
}

export interface Tokens {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface Address {
  id: number
  label: string
  line1: string
  line2: string | null
  city: string
  postal_code: string
  is_default: boolean
}

export type SignupRole = 'customer' | 'restaurant' | 'driver'

/**
 * The venue a restaurant applicant is registering.
 *
 * Collected on the sign-up form rather than afterwards because approval gates
 * login: the account is inactive until an operator approves, so there is no
 * later session in which to fill this in — and an operator approving a name and
 * an email would not be reviewing a business at all.
 */
export interface RestaurantSignupInput {
  name: string
  city: string
  address_line: string
  /** The venue's public number, which is not the owner's personal one. */
  phone: string
  cuisine?: string | null
  description?: string | null
  food_type?: FoodType
}

export interface RegisterInput {
  email: string
  phone: string
  first_name: string
  last_name: string
  password: string
  role?: SignupRole
  /** Required when role is 'restaurant', rejected otherwise — the backend
   *  validates both directions, so sending it for a customer is a 422. */
  restaurant?: RestaurantSignupInput
}

export interface AddressInput {
  label: string
  line1: string
  line2?: string | null
  city: string
  postal_code: string
  is_default: boolean
}

/** Partial edit of an existing address; omitted fields are left alone. */
export type AddressUpdate = Partial<AddressInput>

export type ProfileUpdate = Partial<Pick<User, 'first_name' | 'last_name' | 'phone'>>

export const authApi = {
  register: (input: RegisterInput) =>
    request<User>('/auth/register', { method: 'POST', body: input }),

  login: (email: string, password: string) =>
    request<Tokens>('/auth/login', { method: 'POST', body: { email, password } }),

  forgotPassword: (email: string) =>
    request<{ message: string; debug_token?: string }>('/auth/forgot-password', {
      method: 'POST',
      body: { email },
    }),

  resetPassword: (token: string, new_password: string) =>
    request<void>('/auth/reset-password', { method: 'POST', body: { token, new_password } }),

  // Sent with auth so the backend revokes the access token as well as the
  // refresh token — clearing storage alone leaves the bearer usable.
  logout: (refresh_token: string) =>
    request<void>('/auth/logout', { method: 'POST', body: { refresh_token }, auth: true }),

  changePassword: (current_password: string, new_password: string) =>
    request<Tokens>('/users/me/change-password', {
      method: 'POST',
      body: { current_password, new_password },
      auth: true,
    }),

  me: () => request<User>('/users/me', { auth: true }),

  updateProfile: (input: ProfileUpdate) =>
    request<User>('/users/me', { method: 'PATCH', body: input, auth: true }),

  listAddresses: () => request<Address[]>('/users/me/addresses', { auth: true }),

  addAddress: (input: AddressInput) =>
    request<Address>('/users/me/addresses', { method: 'POST', body: input, auth: true }),

  updateAddress: (id: number, input: AddressUpdate) =>
    request<Address>(`/users/me/addresses/${id}`, { method: 'PATCH', body: input, auth: true }),

  deleteAddress: (id: number) =>
    request<void>(`/users/me/addresses/${id}`, { method: 'DELETE', auth: true }),
}
