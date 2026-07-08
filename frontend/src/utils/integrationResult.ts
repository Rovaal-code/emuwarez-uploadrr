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
  rate_limited: '⏳ Demasiadas pruebas',
  unexpected_error: '✗ Error inesperado',
}

// Statuses that mean the probe never reached the network (so the client must
// NOT start a cooldown — the backend didn't record a timestamp either).
const EMU_TEST_NO_NETWORK = new Set(['not_configured', 'invalid_url'])

/**
 * How many seconds the eMuwarez "Probar conexión" button should stay on
 * cooldown after a given result, mirroring the backend's 1/minute limit
 * (services/integration_tests.py::MIN_EMU_TEST_SECONDS).
 */
export function emuTestCooldownSeconds(result: IntegrationTestResult): number {
  if (result.status === 'rate_limited') {
    const wait = Number(result.details?.wait_seconds)
    return Number.isFinite(wait) && wait > 0 ? wait : 60
  }
  if (EMU_TEST_NO_NETWORK.has(result.status)) return 0
  return 60
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
