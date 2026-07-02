import { api } from './client'
import type { IntegrationTestResult } from './integrationTests'

export function testDiscordNotification(params: { webhook_url?: string } = {}): Promise<IntegrationTestResult> {
  return api.post<IntegrationTestResult>('/notifications/test/discord', params)
}

export function testTelegramNotification(params: { bot_token?: string; chat_id?: string } = {}): Promise<IntegrationTestResult> {
  return api.post<IntegrationTestResult>('/notifications/test/telegram', params)
}
