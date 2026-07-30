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

  // fetch only REJECTS when the request never completed at all: DNS/TLS
  // failure, connection reset, a cross-origin redirect (a Cloudflare Access
  // interstitial in front of /api does exactly this), or an extension
  // cancelling it. Every real HTTP answer — including a 403 from a WAF or a
  // 502/524 from a proxy — resolves and is turned into an ApiClientError
  // below.
  //
  // Wrapped here as status 0 so callers see ONE error type and can tell "never
  // reached the server" apart from a real HTTP status, instead of having to
  // sniff for the browser-specific "Failed to fetch" message. Before this,
  // that TypeError escaped as-is and every caller's `instanceof
  // ApiClientError` branch missed it — LoginPage's own "no se pudo conectar"
  // case was unreachable for that reason, and a proxy problem surfaced as a
  // bare "Error inesperado".
  let resp: Response
  try {
    resp = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (err) {
    throw new ApiClientError(
      'No se pudo conectar con el servidor: la petición no llegó a completarse.',
      0,
      err,
    )
  }

  if (resp.status === 401) {
    clearToken()
    unauthorizedHandler?.()
    throw new ApiClientError('No autorizado', 401, null)
  }

  // Reading the body can fail too, and for the same kind of reason: a proxy
  // that truncates the response, or one that answers with an HTML error page
  // while still claiming application/json. Wrapped so it surfaces as a normal
  // ApiClientError instead of a raw SyntaxError nobody upstream catches.
  let data: unknown
  const ct = resp.headers.get('content-type') ?? ''
  try {
    data = ct.includes('application/json') ? await resp.json() : await resp.text()
  } catch (err) {
    throw new ApiClientError(
      `El servidor respondió con algo que no se pudo leer (HTTP ${resp.status}).`,
      resp.status,
      err,
    )
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
