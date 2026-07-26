// Base API client with auth token support

const TOKEN_KEY = 'emuwarez_uploadrr_token'
const BASE_URL = '/api'

// "Recordarme" on LoginPage decides which storage the token lives in:
// localStorage survives closing the browser, sessionStorage is gone as soon
// as the tab/window closes. Only one copy ever exists at a time.
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY) ?? sessionStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string, remember: boolean = true): void {
  if (remember) {
    localStorage.setItem(TOKEN_KEY, token)
    sessionStorage.removeItem(TOKEN_KEY)
  } else {
    sessionStorage.setItem(TOKEN_KEY, token)
    localStorage.removeItem(TOKEN_KEY)
  }
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(TOKEN_KEY)
}

// A 401 from ANY request wipes the token below — but until this handler was
// added, nothing told the rest of the app the session had just died: App.tsx
// only checks auth once at boot, so a component whose own request 401'd kept
// showing its own local "no autorizado" error while the rest of the SPA sat
// there as if still logged in, until a manual refresh re-ran the boot check
// and finally bounced to /login. Registered by App.tsx so any 401, anywhere,
// bounces to the login screen right away instead of leaving a half-dead page.
let unauthorizedHandler: (() => void) | null = null

export function setUnauthorizedHandler(fn: (() => void) | null): void {
  unauthorizedHandler = fn
}

export class ApiClientError extends Error {
  status: number
  body: unknown

  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.name = 'ApiClientError'
    this.status = status
    this.body = body
  }
}

// FastAPI's `detail` is a plain string for hand-raised HTTPExceptions, but a
// list of Pydantic error objects ({loc, msg, type, ...}) for 422 validation
// failures — stringifying that list directly renders as "[object Object]".
function extractErrorDetail(data: unknown, fallback: string): string {
  if (typeof data !== 'object' || data === null || !('detail' in data)) return fallback
  const detail = (data as { detail: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map(item => (item && typeof item === 'object' && 'msg' in item) ? String((item as { msg: unknown }).msg) : null)
      .filter((m): m is string => Boolean(m))
      // Pydantic prefixes messages raised via `raise ValueError(...)` in a
      // field_validator with "Value error, " — strip it, our own messages
      // are already written to stand on their own.
      .map(m => m.replace(/^Value error,\s*/, ''))
    if (messages.length) return messages.join('; ')
  }
  return fallback
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  skipAuth?: boolean
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, skipAuth = false } = options

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }

  if (!skipAuth) {
    const token = getToken()
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
  }

  const resp = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (resp.status === 401) {
    clearToken()
    unauthorizedHandler?.()
    throw new ApiClientError('No autorizado', 401, null)
  }

  let data: unknown
  const ct = resp.headers.get('content-type') ?? ''
  if (ct.includes('application/json')) {
    data = await resp.json()
  } else {
    data = await resp.text()
  }

  if (!resp.ok) {
    throw new ApiClientError(extractErrorDetail(data, resp.statusText), resp.status, data)
  }

  return data as T
}

export const api = {
  get: <T>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'GET' }),
  post: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method'>) =>
    request<T>(path, { ...opts, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method'>) =>
    request<T>(path, { ...opts, method: 'PATCH', body }),
  put: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method'>) =>
    request<T>(path, { ...opts, method: 'PUT', body }),
  delete: <T>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'DELETE' }),
}
