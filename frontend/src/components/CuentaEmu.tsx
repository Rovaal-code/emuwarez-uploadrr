import { useState } from 'react'
import { tapar, usePerfilEmu } from '../context/PerfilEmuContext'
import { useCooldown } from '../hooks/useCooldown'
import { decimalEs, enlacesCuentaEmu, ratioBajo } from '../utils/cuentaEmu'
import { formatNumero, timeAgo } from '../utils/format'
import { IconoAviso, IconoCampana, IconoCorreo, IconoSubida } from './Iconos'
import { ServiceIcon } from './ServiceIcon'
import { Tooltip } from './Tooltip'

const AVISO_RATIO = 'Con ratio por debajo de 1, eMuwarez desactiva la API key: la app deja de poder sincronizar y subir.'
const OTRA_PESTANA = <span className="solo-lector"> (se abre en otra pestaña)</span>

// Tu cuenta de eMuwarez en la cabecera del Panel: quién eres, tus cifras y los
// enlaces a lo que la API no da (mensajes, notificaciones).
export function CuentaEmu() {
  const { perfil, actualizar, ocultarNombre } = usePerfilEmu()
  const espera = useCooldown()
  const [actualizando, setActualizando] = useState(false)
  // Sin usuario aún (la primera lectura ha fallado) se enseña al menos el error.
  if (!perfil || (!perfil.username && !perfil.error)) return null

  const enlaces = perfil.username ? { usuario: perfil.username, ...enlacesCuentaEmu(perfil.username) } : null
  const bajo = ratioBajo(perfil.ratio)
  const hr = perfil.hit_and_runs ?? 0

  const pulsar = async () => {
    setActualizando(true)
    try { await actualizar() } catch { /* se queda lo que había */ } finally {
      setActualizando(false)
      espera.start(60)  // el servidor tampoco vuelve a eMuwarez antes de un minuto
    }
  }

  const cifra = (etiqueta: string, valor: React.ReactNode, clase = '') => (
    <div className={`cuenta-emu-cifra ${clase}`}><dt>{etiqueta}</dt><dd>{valor}</dd></div>
  )

  return (
    <section className="cuenta-emu" aria-label="Tu cuenta en eMuwarez">
      {enlaces && (
        <a className="cuenta-emu-usuario hover-link" href={enlaces.perfil} target="_blank" rel="noreferrer">
          <ServiceIcon type="emu" size={16} />
          {ocultarNombre ? tapar(enlaces.usuario) : enlaces.usuario}
          <span className="solo-lector"> (tu perfil en eMuwarez, se abre en otra pestaña)</span>
        </a>
      )}
      {perfil.group && <span className="badge cuenta-emu-rol">{perfil.group}</span>}

      {perfil.ratio != null && (
        <dl className="cuenta-emu-cifras">
          {cifra('Ratio', bajo
            ? <Tooltip content={AVISO_RATIO}><span tabIndex={0}><IconoAviso /> {decimalEs(perfil.ratio)}</span></Tooltip>
            : decimalEs(perfil.ratio), bajo ? 'es-malo' : '')}
          {perfil.uploaded && cifra('Subido', decimalEs(perfil.uploaded))}
          {perfil.downloaded && cifra('Bajado', decimalEs(perfil.downloaded))}
          {perfil.buffer && cifra('Buffer', decimalEs(perfil.buffer))}
          {cifra('Sembrando', formatNumero(perfil.seeding))}
          {cifra('Descargando', formatNumero(perfil.leeching))}
          {cifra('BON', formatNumero(perfil.seedbonus))}
          {cifra('H&R', hr > 0 ? <><IconoAviso /> {formatNumero(hr)}</> : formatNumero(hr), hr > 0 ? 'es-aviso' : '')}
        </dl>
      )}

      {perfil.error && (
        <span className="cuenta-emu-error" role="status"><IconoAviso /> {perfil.error}</span>
      )}

      {enlaces && (
        <nav className="cuenta-emu-enlaces" aria-label="Enlaces de tu cuenta en eMuwarez">
          <a className="hover-link" href={enlaces.mensajes} target="_blank" rel="noreferrer"><IconoCorreo /> Mensajes{OTRA_PESTANA}</a>
          <a className="hover-link" href={enlaces.notificaciones} target="_blank" rel="noreferrer"><IconoCampana /> Notificaciones{OTRA_PESTANA}</a>
          <a className="hover-link" href={enlaces.subidas} target="_blank" rel="noreferrer"><IconoSubida /> Mis subidas{OTRA_PESTANA}</a>
        </nav>
      )}

      {perfil.configured && (
        <Tooltip content={`${perfil.updated_at ? `Leído de eMuwarez ${timeAgo(perfil.updated_at)}` : 'Aún sin leer de eMuwarez'}. Se vuelve a leer solo cada hora.`}>
          <button type="button" className="btn btn-ghost btn-sm" onClick={pulsar}
            disabled={actualizando || espera.active} aria-label="Actualizar tu cuenta de eMuwarez">
            {actualizando ? <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> : '↻'}
          </button>
        </Tooltip>
      )}
    </section>
  )
}
