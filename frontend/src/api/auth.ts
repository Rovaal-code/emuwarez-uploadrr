import { api, setToken, clearToken } from './client'
import type { LoginResponse, CurrentUserResponse } from '../types/api'

export async function login(username: string, password: string): Promise<LoginResponse> {
  const resp = await api.post<LoginResponse>('/auth/login', { username, password }, { skipAuth: true })
  setToken(resp.token)
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
