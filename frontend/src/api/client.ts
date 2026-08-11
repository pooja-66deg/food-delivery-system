// Thin fetch wrapper around the backend API.
//
// In dev, requests go to "/api/*" which Vite proxies to the FastAPI server
// (see vite.config.ts). In production, set VITE_API_URL to the API base
// *including* the /api prefix — e.g. https://api-gateway.example.run.app/api,
// not the bare origin. Every gateway route is mounted under /api/, and the
// fallback below is a path for the same reason.

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api'

export class ApiError extends Error {
  status: number
  details: unknown

  constructor(message: string, status: number, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

/**
 * Message to show the user for a caught error.
 *
 * An ApiError already carries a message the backend wrote for humans, so it is
 * shown as-is. Anything else is an unexpected failure whose message would mean
 * nothing to a user, so the caller's fallback wins.
 */
export function errorMessage(err: unknown, fallback = 'Something went wrong.'): string {
  return err instanceof ApiError ? err.message : fallback
}

let tokenGetter: () => string | null = () => null
let adminTokenGetter: () => string | null = () => localStorage.getItem('fd_admin_token')
let logoutHandler: (() => void) | null = null

/** Register how the client obtains the current access token. */
export function setTokenGetter(fn: () => string | null): void {
  tokenGetter = fn
}

/** Register how to get the admin token. */
export function setAdminTokenGetter(fn: () => string | null): void {
  adminTokenGetter = fn
}

/** Register a handler to call when the API returns 401 (invalid/expired token). */
export function setLogoutHandler(fn: () => void): void {
  logoutHandler = fn
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  auth?: boolean
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, auth = false } = opts
  const headers: Record<string, string> = {}

  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth) {
    // Use admin token for admin API calls (paths containing /admin/)
    // Otherwise use user token
    const isAdminPath = path.includes('/admin/')
    const token = isAdminPath ? adminTokenGetter() : tokenGetter()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }

  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError('Cannot reach the server. Is the backend running?', 0)
  }

  if (res.status === 204) return undefined as T

  const data = await res.json().catch(() => null)
  if (!res.ok) {
    if (res.status === 401 && logoutHandler) {
      logoutHandler()
    }
    throw new ApiError(extractMessage(data) ?? `Request failed (${res.status})`, res.status, data)
  }
  return data as T
}

/** POST a single file as multipart/form-data (field name "file"), with auth. */
export async function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData()
  form.append('file', file)
  const headers: Record<string, string> = {}
  const token = tokenGetter()
  if (token) headers['Authorization'] = `Bearer ${token}`

  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, { method: 'POST', headers, body: form })
  } catch {
    throw new ApiError('Cannot reach the server. Is the backend running?', 0)
  }
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    if (res.status === 401 && logoutHandler) {
      logoutHandler()
    }
    throw new ApiError(extractMessage(data) ?? `Request failed (${res.status})`, res.status, data)
  }
  return data as T
}

function extractMessage(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null
  const detail = (data as Record<string, unknown>).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0] && typeof detail[0] === 'object') {
    const msg = (detail[0] as Record<string, unknown>).msg
    if (typeof msg === 'string') return msg
  }
  return null
}
