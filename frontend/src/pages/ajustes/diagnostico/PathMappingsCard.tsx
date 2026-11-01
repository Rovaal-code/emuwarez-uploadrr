import { useState, useEffect } from 'react'
import { useUnsavedGuard } from '../../../utils/unsavedGuard'
import { fetchSettings, updateSettings } from '../../../api/settings'
import { useTooltip } from '../../../components/Tooltip'
import { useSettingsMessageAdapter } from '../mensajes'

function RemoveMappingRuleButton({ onClick }: { onClick: () => void }) {
  const { triggerProps, tooltipNode } = useTooltip('Quitar regla')
  return (
    <button className="btn btn-ghost btn-sm" type="button" onClick={onClick} {...triggerProps}>✕{tooltipNode}</button>
  )
}

// ---------- Path mappings card (library.path_mappings only) ----------
// Self-contained like AccountCard: its own load/save, untouched by
// ConfigTab's dirty-tracking or "Guardar configuración" button. PUT /settings
// only writes fields it's given, so saving here never touches anything else.
export function PathMappingsCard() {
  const [mappings, setMappings] = useState<{ from: string; to: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const setMsg = useSettingsMessageAdapter()
  const [baseline, setBaseline] = useState('[]')

  useEffect(() => {
    fetchSettings()
      .then(s => {
        const m = s.path_mappings ?? []
        setMappings(m)
        setBaseline(JSON.stringify(m))
      })
      .finally(() => setLoading(false))
  }, [])

  const dirty = JSON.stringify(mappings) !== baseline
  useUnsavedGuard('rutas', dirty)

  async function handleSave() {
    setSaving(true)
    setMsg(null)
    try {
      const cleaned = mappings.map(m => ({ from: m.from.trim(), to: m.to.trim() })).filter(m => m.from && m.to)
      const updated = await updateSettings({ path_mappings: cleaned })
      const m = updated.path_mappings ?? []
      setMappings(m)
      setBaseline(JSON.stringify(m))
      setMsg({ ok: true, text: '✓ Mapeo de rutas guardado' })
    } catch (e: unknown) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="placeholder-card">
      <h3 style={{ marginTop: 0, marginBottom: 6 }}>Mapeo de rutas (biblioteca remota)</h3>
      <p className="form-hint" style={{ marginTop: 0, marginBottom: 12 }}>
        Traduce la ruta que reporta Radarr/Sonarr a la ruta donde la app alcanza el archivo
        (monta la biblioteca por SSHFS/NFS/SMB donde quieras). Se aplica al leer MediaInfo,
        verificar y subir. Sin reglas, no cambia nada.
      </p>
      {loading ? (
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Cargando…</p>
      ) : (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {mappings.length === 0 && (
              <span className="form-hint">No hay reglas. Añade una para acceder a una biblioteca remota.</span>
            )}
            {mappings.map((m, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <input
                  className="form-input" style={{ flex: 1, minWidth: 200 }}
                  value={m.from} placeholder="Ruta de Radarr/Sonarr: /data/media"
                  onChange={e => setMappings(p => p.map((x, j) => j === i ? { ...x, from: e.target.value } : x))}
                />
                <span style={{ color: 'var(--text-muted)' }}>→</span>
                <input
                  className="form-input" style={{ flex: 1, minWidth: 200 }}
                  value={m.to} placeholder="Ruta local: /home/alvaro/mnt/emu-media"
                  onChange={e => setMappings(p => p.map((x, j) => j === i ? { ...x, to: e.target.value } : x))}
                />
                <RemoveMappingRuleButton onClick={() => setMappings(p => p.filter((_, j) => j !== i))} />
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10 }}>
            <button className="btn btn-secondary btn-sm" type="button"
              onClick={() => setMappings(p => [...p, { from: '', to: '' }])}>+ Añadir regla</button>
            <button className="btn btn-primary btn-sm" type="button" onClick={handleSave} disabled={saving || !dirty}>
              {saving ? 'Guardando…' : 'Guardar cambios'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
