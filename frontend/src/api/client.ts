/**
 * Typed API client.
 *
 * Tokens live in httpOnly cookies, so every request is sent with
 * `credentials: 'include'`. A 401 triggers exactly one silent refresh, then the
 * original request is retried; concurrent callers share the same refresh.
 * The API is same-origin by default (Vite proxy in dev, Caddy in prod, or a
 * Vercel rewrite), so no CORS or cookie-domain juggling is needed. Set
 * `VITE_API_BASE_URL` only when the API is served from another origin.
 */

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

export class ApiError extends Error {
  readonly status: number
  readonly fields: Record<string, string>

  constructor(status: number, message: string, fields: Record<string, string> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fields = fields
  }
}

type UnauthorizedHandler = () => void
let onUnauthorized: UnauthorizedHandler = () => {}

export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  onUnauthorized = handler
}

let refreshInFlight: Promise<boolean> | null = null

async function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

async function toApiError(response: Response): Promise<ApiError> {
  let detail = ''
  const fields: Record<string, string> = {}
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') {
      detail = body.detail
    } else if (Array.isArray(body.detail)) {
      for (const item of body.detail as Array<{ loc?: unknown[]; msg?: string }>) {
        const location = (item.loc ?? []).filter((part) => part !== 'body').join('.')
        if (location) fields[location] = item.msg ?? 'Invalid value'
      }
      detail = 'Please check the highlighted fields.'
    }
  } catch {
    detail = response.statusText
  }
  return new ApiError(response.status, detail || 'Request failed', fields)
}

const AUTH_PATHS = [
  '/auth/config',
  '/auth/login',
  '/auth/register',
  '/auth/password',
  '/auth/otp/',
  '/auth/refresh',
  '/auth/logout',
]

function isAuthPath(path: string): boolean {
  return AUTH_PATHS.some((prefix) => path.startsWith(prefix))
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  params?: Record<string, string | number | boolean | undefined | null>
  signal?: AbortSignal
}

function buildPath(path: string, params?: RequestOptions['params']): string {
  if (!params) return path
  const query = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null)
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join('&')
  return query ? `${path}?${query}` : path
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
  allowRefresh = true,
): Promise<T> {
  const { method = 'GET', body, params, signal } = options

  let response: Response
  try {
    response = await fetch(`${API_BASE}${buildPath(path, params)}`, {
      method,
      credentials: 'include',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch {
    throw new ApiError(0, 'Network request failed')
  }

  if (response.status === 401 && allowRefresh && !isAuthPath(path)) {
    const refreshed = await refreshSession()
    if (refreshed) {
      return apiRequest<T>(path, options, false)
    }
    onUnauthorized()
    throw await toApiError(response)
  }

  if (!response.ok) {
    throw await toApiError(response)
  }

  if (response.status === 204) {
    return undefined as T
  }

  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => apiRequest<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'POST', body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'PATCH', body }),
  delete: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'DELETE', body }),
}
