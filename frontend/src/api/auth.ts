import { api, setToken, clearToken } from './client'
import type { LoginResponse, CurrentUserResponse } from '../types/api'

export async function login(username: string, password: string, remember: boolean = true): Promise<LoginResponse> {
  const resp = await api.post<LoginResponse>('/auth/login', { username, password }, { skipAuth: true })
  setToken(resp.token, remember)
  return resp
}

export async function logout(): Promise<void> {
  try {
    await api.post('/auth/logout')
  } finally {
    clearToken()
  }
}

export async function getMe(): Promise<CurrentUserResponse> {
  return api.get<CurrentUserResponse>('/auth/me')
}

export interface ChangeCredentialsResponse {
  username: string
  message: string
}

export async function changeCredentials(body: {
  current_password: string
  new_username?: string
  new_password?: string
}): Promise<ChangeCredentialsResponse> {
  return api.post<ChangeCredentialsResponse>('/auth/change-credentials', body)
}

export interface SesionAbierta {
  id: number
  current: boolean
  created_at: string
  last_used_at: string
  user_agent: string | null
  ip_address: string | null
}

export async function getSessions(): Promise<{ sessions: SesionAbierta[]; inactive_days: number }> {
  return api.get('/auth/sessions')
}

export async function closeOtherSessions(): Promise<{ closed: number }> {
  return api.post('/auth/sessions/close-others')
}
