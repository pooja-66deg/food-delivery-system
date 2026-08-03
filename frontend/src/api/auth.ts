// Typed bindings for the users/auth backend endpoints.

import { request } from './client'

export interface User {
  id: number
  email: string
  phone: string
  first_name: string
  last_name: string
  role: string
  is_active: boolean
  is_email_verified: boolean
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

export interface RegisterInput {
  email: string
  phone: string
  first_name: string
  last_name: string
  password: string
  role?: SignupRole
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

  requestOtp: (phone: string) =>
    request<{ message: string; debug_otp?: string }>('/auth/otp/request', {
      method: 'POST',
      body: { phone },
    }),

  verifyOtp: (phone: string, otp: string) =>
    request<Tokens>('/auth/otp/verify', { method: 'POST', body: { phone, otp } }),

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

  requestEmailVerification: () =>
    request<{ message: string; debug_token?: string }>('/auth/verify-email/request', {
      method: 'POST',
      auth: true,
    }),

  confirmEmailVerification: (token: string) =>
    request<void>('/auth/verify-email/confirm', { method: 'POST', body: { token } }),

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
