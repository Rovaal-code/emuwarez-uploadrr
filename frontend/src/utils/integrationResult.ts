import type { IntegrationTestResult } from '../api/integrationTests'

// Single source of truth for turning a "Probar conexión" result into a
// label + color. Used to live duplicated (and drifting — e.g. only some
// call sites handled 'timeout') across SetupWizard, SettingsPage and
// InstancesPage; now shared so every "Probar conexión" button in the app
// reads the same status the same way.
const STATUS_LABELS: Record<string, string> = {
  not_configured: '⚠ Sin configurar',
  invalid_key: '✗ API key inválida',
  invalid_kind: '✗ Tipo inválido',
  invalid_url: '✗ URL inválida',
  timeout: '✗ Timeout',
  not_found: '✗ No encontrado',
  connection_error: '✗ Error de conexión',
  unexpected_error: '✗ Error inesperado',
}

export function testResultLabel(result: IntegrationTestResult): string {
  if (result.ok) {
    const version = result.details?.version
    const username = result.details?.username
    let label = '✓ Conectado'
    if (version) label += ` (v${version})`
    if (username) label += ` — ${username}`
    return label
  }
  return STATUS_LABELS[result.status] ?? `✗ ${result.message}`
}

export function testResultColor(result: IntegrationTestResult): string {
  if (result.ok) return '#22c55e'
  if (result.status === 'not_configured') return '#f59e0b'
  return '#ef4444'
}
