import { api } from './client'
import type { IntegrationTestResult } from './integrationTests'

export function testDiscordNotification(params: { webhook_url?: string } = {}): Promise<IntegrationTestResult> {
  return api.post<IntegrationTestResult>('/notifications/test/discord', params)
}

export function testTelegramNotification(params: { bot_token?: string; chat_id?: string } = {}): Promise<IntegrationTestResult> {
  return api.post<IntegrationTestResult>('/notifications/test/telegram', params)
}

// --- In-app notification feed (topbar bell) ---

export interface NotificationItem {
  id: number
  event_type: string
  title: string
  body: string | null
  link: string | null
  level: string
  entity_type: string | null
  entity_id: number | null
  created_at: string
  read_at: string | null
  read: boolean
}

export interface NotificationFeed {
  notifications: NotificationItem[]
  unread_count: number
}

export function getNotifications(params: { limit?: number; unread_only?: boolean } = {}): Promise<NotificationFeed> {
  const qs = new URLSearchParams()
  if (params.limit !== undefined) qs.set('limit', String(params.limit))
  if (params.unread_only) qs.set('unread_only', 'true')
  const query = qs.toString()
  return api.get<NotificationFeed>(`/notifications${query ? `?${query}` : ''}`)
}

export function markNotificationRead(id: number): Promise<{ ok: boolean; unread_count: number }> {
  return api.post<{ ok: boolean; unread_count: number }>(`/notifications/${id}/read`, {})
}

export function markAllNotificationsRead(): Promise<{ ok: boolean; unread_count: number }> {
  return api.post<{ ok: boolean; unread_count: number }>('/notifications/read-all', {})
}
