import { api } from './client'

// Clave de solo lectura del widget de Homepage. Solo se ve entera al generarla.
export async function getWidgetKeyStatus(): Promise<{ configurada: boolean }> {
  return api.get('/widget/clave')
}

export async function generateWidgetKey(): Promise<{ clave: string }> {
  return api.post('/widget/clave')
}

export async function removeWidgetKey(): Promise<{ configurada: boolean }> {
  return api.delete('/widget/clave')
}
