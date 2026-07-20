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
