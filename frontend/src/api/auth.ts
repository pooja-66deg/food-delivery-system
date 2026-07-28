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

export interface RegisterInput {
  email: string
  phone: string
  first_name: string
  last_name: string
  password: string
}

export interface AddressInput {
  label: string
  line1: string
  line2?: string | null
  city: string
  postal_code: string
  is_default: boolean
}

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

  me: () => request<User>('/users/me', { auth: true }),

  updateProfile: (input: ProfileUpdate) =>
    request<User>('/users/me', { method: 'PATCH', body: input, auth: true }),

  listAddresses: () => request<Address[]>('/users/me/addresses', { auth: true }),

  addAddress: (input: AddressInput) =>
    request<Address>('/users/me/addresses', { method: 'POST', body: input, auth: true }),

  deleteAddress: (id: number) =>
    request<void>(`/users/me/addresses/${id}`, { method: 'DELETE', auth: true }),
}
