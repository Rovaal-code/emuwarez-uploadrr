import { useState } from 'react'
import type { QueueActionPlan, QueueAvailableAction } from '../types/api'
import { executeSafeAction, getQueueActionEvents } from '../api/operationalQueue'

interface Props {
  itemId: number
  plan: QueueActionPlan | null
  actions: QueueAvailableAction[]
  onNavigate?: (route: string) => void
  onClose?: () => void
}

const FLOW_LABELS: Record<string, string> = {
  nomenclature: 'Adaptar nomenclatura',
  upload_preflight: 'Preflight Uploadrr',
  upload_execution: 'Iniciar subida',
  upload_retry: 'Reintentar subida',
  upload_logs: 'Ver logs de subida',
  filesystem_verify: 'Verificar archivo',
  arr_status: 'Estado descarga ARR',
  arr_diagnostics: 'Diagnóstico ARR',
  context_review: 'Revisión manual',
}

const ROUTE_LABELS: Record<string, string> = {
  '/library': 'Biblioteca',
  '/uploads': 'Subidas',
  '/missing': 'Faltantes',
  '/instances': 'Instancias',
  '/queue': 'Cola',
}

const STATUS_COLORS: Record<string, string> = {
  ready: '#22c55e',
  waiting: '#f59e0b',
  running: '#3b82f6',
  blocked: '#ef4444',
  open: '#6b7280',
}

export function QueueActionPanel({ itemId, plan, actions, onNavigate, onClose }: Props) {
  const [executing, setExecuting] = useState(false)
  const [execResult, setExecResult] = useState<string | null>(null)
  const [events, setEvents] = useState<{status: string; message: string; created_at: string}[]>([])
  const [showEvents, setShowEvents] = useState(false)

  const safeActions = actions.filter(a => a.safe_to_execute_inline)

  async function handleExecuteSafe(action: string) {
    setExecuting(true)
    setExecResult(null)
    try {
      const result = await executeSafeAction(itemId, action)
      if (result.blocked) {
        setExecResult(`Bloqueado: ${result.message}`)
      } else if (result.ok) {
        const r = result.result
        if (r && typeof r.file_exists === 'boolean') {
          setExecResult(r.file_exists ? '✓ Archivo encontrado en disco' : '⚠ Archivo NO encontrado en disco')
        } else {
          setExecResult(`✓ Acción '${action}' completada`)
        }
      } else {
        setExecResult(`Error: ${result.error ?? 'desconocido'}`)
      }
    } catch { setExecResult('Error al ejecutar la acción') }
    finally { setExecuting(false) }
  }

  async function loadEvents() {
    try {
      const data = await getQueueActionEvents(itemId, 10)
      setEvents(data.events.map(e => ({ status: e.status, message: e.message ?? '', created_at: e.created_at })))
      setShowEvents(true)
    } catch { /* ignore */ }
  }

  if (!plan) return null

  const statusColor = STATUS_COLORS[plan.status] ?? '#6b7280'
  const routeLabel = ROUTE_LABELS[plan.ui.route] ?? plan.ui.route

  return (
    <div style={{
      background: 'rgba(17,24,39,0.98)',
      border: '1px solid rgba(255,255,255,0.12)',
      borderLeft: `3px solid ${statusColor}`,
      borderRadius: 8,
      padding: '14px 16px',
      fontSize: '0.82rem',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <div style={{ fontWeight: 600, color: '#f3f4f6' }}>
          Plan de acción · item #{itemId}
        </div>
        {onClose && (
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: '1rem' }}>✕</button>
        )}
      </div>

      {/* Action summary */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 16px', marginBottom: 10 }}>
        <div>
          <span style={{ color: '#9ca3af' }}>Acción: </span>
          <strong style={{ color: '#e5e7eb' }}>{plan.action}</strong>
        </div>
        <div>
          <span style={{ color: '#9ca3af' }}>Flow: </span>
          <span style={{ color: '#e5e7eb' }}>{FLOW_LABELS[plan.flow] ?? plan.flow}</span>
        </div>
        <div>
          <span style={{ color: '#9ca3af' }}>Estado: </span>
          <span style={{ color: statusColor, fontWeight: 600 }}>{plan.status}</span>
        </div>
      </div>

      {/* UI route guidance */}
      <div style={{
        background: 'rgba(59,130,246,0.1)',
        border: '1px solid rgba(59,130,246,0.3)',
        borderRadius: 6,
        padding: '8px 12px',
        marginBottom: 10,
      }}>
        <div style={{ color: '#93c5fd', fontSize: '0.78rem', marginBottom: 4 }}>Dónde ejecutar esta acción:</div>
        <div style={{ color: '#e5e7eb' }}>
          <strong>{plan.ui.label}</strong>
          {plan.ui.modal && <span style={{ color: '#9ca3af' }}> → modal: {plan.ui.modal}</span>}
        </div>
        {plan.requires_confirmation && (
          <div style={{ color: '#fbbf24', fontSize: '0.75rem', marginTop: 4 }}>
            Requiere confirmación · token: <code style={{ background: 'rgba(255,255,255,0.08)', padding: '1px 4px', borderRadius: 3 }}>{plan.confirmation_token}</code>
          </div>
        )}
        {onNavigate && (
          <button
            onClick={() => onNavigate(plan.ui.route)}
            style={{
              marginTop: 6,
              background: 'rgba(59,130,246,0.2)',
              border: '1px solid rgba(59,130,246,0.5)',
              color: '#93c5fd',
              borderRadius: 5,
              padding: '4px 10px',
              cursor: 'pointer',
              fontSize: '0.75rem',
            }}
          >
            Abrir en {routeLabel} →
          </button>
        )}
      </div>

      {/* Blockers / reasons */}
      {plan.blockers.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ color: '#ef4444', fontSize: '0.75rem', marginBottom: 2 }}>Bloqueadores:</div>
          {plan.blockers.map((b, i) => <div key={i} style={{ color: '#fca5a5', paddingLeft: 10 }}>· {b}</div>)}
        </div>
      )}
      {plan.reasons.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ color: '#9ca3af', fontSize: '0.75rem', marginBottom: 2 }}>Razones:</div>
          {plan.reasons.map((r, i) => <div key={i} style={{ color: '#d1d5db', paddingLeft: 10 }}>· {r}</div>)}
        </div>
      )}

      {/* Safe inline actions */}
      {safeActions.length > 0 && (
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 10, marginTop: 6 }}>
          <div style={{ color: '#9ca3af', fontSize: '0.74rem', marginBottom: 6 }}>Acciones seguras (sin confirmación):</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {safeActions.map(a => (
              <button
                key={a.action}
                disabled={executing}
                onClick={() => handleExecuteSafe(a.action)}
                style={{
                  background: 'rgba(16,185,129,0.15)',
                  border: '1px solid rgba(16,185,129,0.4)',
                  color: '#6ee7b7',
                  borderRadius: 5,
                  padding: '4px 10px',
                  cursor: executing ? 'wait' : 'pointer',
                  fontSize: '0.75rem',
                }}
              >
                {executing ? '…' : a.label}
              </button>
            ))}
          </div>
          {execResult && (
            <div style={{
              marginTop: 8,
              padding: '6px 10px',
              background: execResult.startsWith('✓') ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.1)',
              border: `1px solid ${execResult.startsWith('✓') ? 'rgba(16,185,129,0.3)' : 'rgba(245,158,11,0.3)'}`,
              borderRadius: 5,
              color: execResult.startsWith('✓') ? '#6ee7b7' : '#fcd34d',
              fontSize: '0.78rem',
            }}>
              {execResult}
            </div>
          )}
        </div>
      )}

      {/* Events */}
      <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 8, marginTop: 8 }}>
        <button
          onClick={loadEvents}
          style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: '0.74rem', padding: 0 }}
        >
          {showEvents ? '▲ Ocultar eventos' : '▼ Ver historial de eventos'}
        </button>
        {showEvents && events.length === 0 && (
          <div style={{ color: '#6b7280', fontSize: '0.75rem', marginTop: 4 }}>Sin eventos registrados.</div>
        )}
        {showEvents && events.map((ev, i) => (
          <div key={i} style={{ fontSize: '0.74rem', color: '#9ca3af', marginTop: 3 }}>
            <span style={{ color: ev.status === 'ok' ? '#6ee7b7' : '#fca5a5' }}>
              {ev.status === 'ok' ? '✓' : '⚠'}
            </span>
            {' '}{ev.created_at.slice(0, 19)} · {ev.message}
          </div>
        ))}
      </div>
    </div>
  )
}
