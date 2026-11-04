import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ErrorDeCarga } from './ErrorDeCarga'
import { useConfigForm, type ConfigForm } from './config/useConfigForm'
import { useSeccionActiva } from './config/useSeccionActiva'
import { IndiceSecciones } from './config/IndiceSecciones'
import { BarraGuardado } from './config/BarraGuardado'
import { SeccionAvanzado } from './config/SeccionAvanzado'
import { AccountCard } from './config/AccountCard'
import { SessionsCard } from './config/SessionsCard'
import { WidgetCard } from './config/WidgetCard'
import { EmuwarezCard } from './config/EmuwarezCard'
import { TmdbCard } from './config/TmdbCard'
import { QbitCard } from './config/QbitCard'
import { ProveedoresVideoCard } from './config/ProveedoresVideoCard'
import { ProveedoresImagenesCard } from './config/ProveedoresImagenesCard'
import { BibliotecaCard } from './config/BibliotecaCard'
import { OtrosCard } from './config/OtrosCard'

const TARJETAS: { id: string; titulo: string; tarjeta: (form: ConfigForm) => ReactNode }[] = [
  { id: 'cuenta', titulo: 'Cuenta', tarjeta: () => <AccountCard /> },
  { id: 'sesiones', titulo: 'Sesiones abiertas', tarjeta: () => <SessionsCard /> },
  { id: 'emuwarez', titulo: 'eMuwarez', tarjeta: form => <EmuwarezCard form={form} /> },
  { id: 'tmdb', titulo: 'TMDb', tarjeta: form => <TmdbCard form={form} /> },
  { id: 'qbittorrent', titulo: 'qBittorrent', tarjeta: form => <QbitCard form={form} /> },
  { id: 'proveedores-video', titulo: 'Proveedores de vídeo', tarjeta: form => <ProveedoresVideoCard form={form} /> },
  { id: 'proveedores-imagenes', titulo: 'Proveedores de imágenes', tarjeta: form => <ProveedoresImagenesCard form={form} /> },
  { id: 'otros', titulo: 'Otros', tarjeta: form => <OtrosCard form={form} /> },
  { id: 'widget', titulo: 'Widget para Homepage', tarjeta: () => <WidgetCard /> },
]
const AVANZADO = { id: 'avanzado', titulo: 'Avanzado' }
const ENTRADAS = [...TARJETAS.map(({ id, titulo }) => ({ id, titulo })), AVANZADO]
const IDS = ENTRADAS.map(e => e.id)

const normalizar = (t: string) => t.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim()

export function ConfigTab() {
  const form = useConfigForm()

  if (form.loading) return <p className="aj-cargando">Cargando…</p>
  if (form.errorCarga) {
    return (
      <div className="aj-cargando">
        <ErrorDeCarga mensaje={`No se pudo cargar la configuración: ${form.errorCarga}`} onReintentar={form.reintentar} />
      </div>
    )
  }
  return <ConfigFormulario form={form} />
}

function ConfigFormulario({ form }: { form: ConfigForm }) {
  const raiz = useRef<HTMLDivElement>(null)
  const [consulta, setConsulta] = useState('')
  // Los ids de las secciones cuyo título o etiquetas de campo contienen la consulta; null sin consulta.
  const [coinciden, setCoinciden] = useState<Set<string> | null>(null)
  const [avanzadoAbierto, setAvanzadoAbierto] = useState(false)
  const [resaltada, setResaltada] = useState<string | null>(null)
  const { activa, elegir } = useSeccionActiva(IDS, raiz)

  useEffect(() => {
    const q = normalizar(consulta)
    if (!q) { setCoinciden(null); return }
    const ids = new Set<string>()
    raiz.current?.querySelectorAll<HTMLElement>('[data-seccion]').forEach(el => {
      const etiquetas = [...el.querySelectorAll('h3, label')].map(n => n.textContent ?? '')
      const titulo = ENTRADAS.find(e => e.id === el.dataset.seccion)?.titulo ?? ''
      if (normalizar([titulo, ...etiquetas].join(' ')).includes(q)) ids.add(el.dataset.seccion!)
    })
    setCoinciden(ids)
    // Una búsqueda que acierta dentro de Avanzado la abre.
    if (ids.has(AVANZADO.id)) setAvanzadoAbierto(true)
  }, [consulta])

  useEffect(() => {
    if (!resaltada) return
    const t = window.setTimeout(() => setResaltada(null), 1600)
    return () => window.clearTimeout(t)
  }, [resaltada])

  const visible = (id: string) => coinciden === null || coinciden.has(id)

  function saltar(id: string) {
    elegir(id)
    if (id === AVANZADO.id) setAvanzadoAbierto(true)
    requestAnimationFrame(() => {
      const el = raiz.current?.querySelector<HTMLElement>(`[data-seccion="${id}"]`)
      if (!el) return
      const reducido = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      el.scrollIntoView?.({ behavior: reducido ? 'auto' : 'smooth', block: 'start' })
      el.focus({ preventScroll: true })
      setResaltada(id)
    })
  }

  const seccion = (id: string, contenido: ReactNode) => (
    <div
      key={id}
      id={`aj-seccion-${id}`}
      data-seccion={id}
      tabIndex={-1}
      hidden={!visible(id)}
      className={`aj-seccion${resaltada === id ? ' aj-seccion--resaltada' : ''}`}
    >
      {contenido}
    </div>
  )

  return (
    <div ref={raiz} data-tour="settings-content" className="aj-config">
      <IndiceSecciones
        entradas={ENTRADAS.filter(e => visible(e.id))}
        activa={activa}
        consulta={consulta}
        onConsulta={setConsulta}
        onSaltar={saltar}
      />
      <div className="aj-config__contenido">
        {coinciden?.size === 0 && (
          <p role="status" className="form-hint aj-config__vacio">Ninguna sección coincide con «{consulta.trim()}».</p>
        )}
        {/* Nueve tarjetas en cuatro columnas de ancho: cada una con el alto que
            le pida su contenido (ver settings-config-grid en dashboard.css). La
            página entera se desplaza si no caben todas, no cada tarjeta por
            separado. */}
        <div className="settings-config-grid">
          {TARJETAS.map(t => seccion(t.id, t.tarjeta(form)))}
        </div>
        {seccion(AVANZADO.id, (
          <SeccionAvanzado
            abierta={avanzadoAbierto}
            onAlternar={() => setAvanzadoAbierto(a => !a)}
          >
            <BibliotecaCard form={form} />
          </SeccionAvanzado>
        ))}
      </div>
      {(form.cambios > 0 || form.saving) && (
        <BarraGuardado cambios={form.cambios} guardando={form.saving} onGuardar={form.handleSave} />
      )}
    </div>
  )
}
