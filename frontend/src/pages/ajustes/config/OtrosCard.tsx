import { useState } from 'react'
import { getUploadConcurrencyEstimate, type UploadConcurrencyEstimate } from '../../../api/system'
import { InfoIcon } from '../../../components/InfoIcon'
import { Modal } from '../../../components/Modal'
import { TAMANOS, TAMANO_POR_DEFECTO, tamanoUi, guardarTamano } from '../../../utils/uiScale'
import { MODOS_PISTAS, normalizarModo } from '../../../utils/modoPistas'
import type { ConfigForm } from './useConfigForm'

export function OtrosCard({ form }: { form: ConfigForm }) {
  const { modoDePistas, setModoDePistas, sinCopiasReflink, setSinCopiasReflink, sourceEngine, setSourceEngine, addLogo, setAddLogo, capturasPorCapitulo, setCapturasPorCapitulo, uploadMaxConcurrent, setUploadMaxConcurrent, ignoreSpecials, setIgnoreSpecials, recentLimit, setRecentLimit } = form
  // Tamaño de interfaz. Arranca de lo que ya está aplicado (utils/uiScale lo
  // puso al cargar la página desde localStorage), no de un valor por defecto:
  // si no, el desplegable diría 100% mientras la interfaz está al 130%.
  const [tamanoInterfaz, setTamanoInterfaz] = useState(tamanoUi)
  const [testingConcurrency, setTestingConcurrency] = useState(false)
  const [concurrencyEstimate, setConcurrencyEstimate] = useState<UploadConcurrencyEstimate | null>(null)

  async function handleTestConcurrency() {
    setTestingConcurrency(true)
    setConcurrencyEstimate(null)
    try {
      const r = await getUploadConcurrencyEstimate()
      setConcurrencyEstimate(r)
    } catch {
      // Silently give up — the button itself just goes back to idle, same
      // as any other "Probar…" button here when the request fails.
    } finally {
      setTestingConcurrency(false)
    }
  }

  return (
    <div className="placeholder-card">
      <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
        <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth="1.75" aria-hidden>
          <line x1="4" y1="21" x2="4" y2="14" /><line x1="4" y1="10" x2="4" y2="3" />
          <line x1="12" y1="21" x2="12" y2="12" /><line x1="12" y1="8" x2="12" y2="3" />
          <line x1="20" y1="21" x2="20" y2="16" /><line x1="20" y1="12" x2="20" y2="3" />
          <line x1="1" y1="14" x2="7" y2="14" /><line x1="9" y1="8" x2="15" y2="8" /><line x1="17" y1="16" x2="23" y2="16" />
        </svg>
        Otros
      </h3>
      <div className="form-group">
        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          Renombrar/Ordenar pistas
          <InfoIcon text="Qué se le hace a las pistas de audio y subtítulos antes de subir. Renombrar les pone nombre siguiendo las reglas de eMuwarez y cambia solo la cabecera del archivo: es casi instantáneo por grande que sea. Reordenar las coloca en orden (Español, Català, Inglés, resto) y obliga a reescribir el contenedor entero, y tarda en proporción al tamaño. Si el archivo lo comparte un torrent (un hardlink), no se escribe en él: renombrar y el título interno se hacen en una copia por reflink en la carpeta de subidas (o se omiten, con «No hacer nunca copias reflink») y reordenar se omite. Con Ninguno el archivo se sube tal cual, sin tocar tampoco el título interno. En los tres primeros se marca la pista predeterminada, que es lo que decide qué audio suena al abrirlo." />
        </label>
        <select className="form-input form-select" value={modoDePistas}
                onChange={e => setModoDePistas(normalizarModo(e.target.value))}>
          {MODOS_PISTAS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor="sin-copias-reflink" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          No hacer nunca copias reflink
          <InfoIcon text="Si el archivo lo comparte un torrent o la biblioteca (un hardlink), renombrar las pistas y poner el título interno se hacen en una copia por reflink dentro de la carpeta de subidas, para no tocar el original. Activado, nunca se hace esa copia: esas ediciones se omiten con un aviso en el registro de la subida y se sube el archivo tal cual, con un enlace duro. Un archivo que no comparte nadie se sigue editando en su sitio." />
        </label>
        <select id="sin-copias-reflink" className="form-input form-select" value={sinCopiasReflink ? 'true' : 'false'} onChange={e => setSinCopiasReflink(e.target.value === 'true')}>
          <option value="false">Desactivado</option>
          <option value="true">Activado</option>
        </select>
      </div>        {/* El único ajuste de esta pestaña que NO se guarda con el botón: es
          de este navegador, no de la instalación, y se aplica y se recuerda
          al elegirlo. Ver utils/uiScale.ts. */}
      <div className="form-group">
        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          Tamaño de interfaz
          <InfoIcon text="Agranda o encoge la interfaz entera, para ajustarla a tu pantalla. La misma resolución se ve muy distinta según el tamaño del monitor y a la distancia que lo tengas, así que aquí no se adivina nada: lo eliges tú y se aplica al momento. Se guarda solo en este navegador, así que puedes tener un tamaño en el sobremesa y otro en el portátil, y no entra en el backup de configuración." />
        </label>
        <select className="form-input form-select" value={tamanoInterfaz}
                onChange={e => setTamanoInterfaz(guardarTamano(Number(e.target.value)))}>
          {TAMANOS.map(t => (
            <option key={t} value={t}>{t}%{t === TAMANO_POR_DEFECTO ? ' (por defecto)' : ''}</option>
          ))}
        </select>
      </div>
      <div className="form-group">
        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          Internal Source Tool
          <InfoIcon text="Herramienta interna que deduce el source analizando el archivo real con MediaInfo, FFprobe y MKVToolNix, sin mirar el nombre. Todavía está en desarrollo y puede ser inexacta, por eso viene desactivada. Activada, añade su columna a la comparación de Source y participa en el aviso de discrepancia. Desactivada, esa columna sale vacía y el aviso compara solo el nombre del archivo con Radarr/Sonarr; el source final no cambia salvo en archivos donde ni el nombre ni Radarr/Sonarr dicen nada, que siguen usando la estimación por bitrate de siempre." />
        </label>
        <select className="form-input form-select" value={sourceEngine ? 'true' : 'false'} onChange={e => setSourceEngine(e.target.value === 'true')}>
          <option value="false">Desactivada</option>
          <option value="true">Activada</option>
        </select>
      </div>
      <div className="form-group">
        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          Subir el logo del contenido
          <InfoIcon text="Incrusta el logo del contenido al principio de la descripción del torrent, en español cuando TMDb lo tiene en ese idioma. Desactivado, la descripción se sube sin logo; el resto (capturas, ficha técnica y tráiler) no cambia." />
        </label>
        <select className="form-input form-select" value={addLogo ? 'true' : 'false'} onChange={e => setAddLogo(e.target.value === 'true')}>
          <option value="true">Sí</option>
          <option value="false">No</option>
        </select>
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor="capturas-de-los-packs" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          Capturas de los packs
          <InfoIcon text="En un pack de temporada o de serie completa, de qué capítulos genera y sube capturas Uploadrr. Por defecto, solo del primero (el de número más bajo, sin contar los especiales si el pack trae otra temporada). Con todos los capítulos, cada uno lleva además las suyas en un desplegable de la descripción, y con muchos capítulos la subida tarda bastante más." />
        </label>
        <select id="capturas-de-los-packs" className="form-input form-select" value={capturasPorCapitulo ? 'true' : 'false'} onChange={e => setCapturasPorCapitulo(e.target.value === 'true')}>
          <option value="false">Solo del primer capítulo</option>
          <option value="true">De todos los capítulos</option>
        </select>
      </div>
      <div className="form-group">
        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          Máximo de Subidas en Paralelo
          <InfoIcon text="Cuántas subidas pueden estar en curso a la vez, de principio a fin (verificación previa, nomenclatura, remux, hasheo del torrent y transferencia a eMuwarez). No es solo una cola visual: las demás no dan ni un paso hasta que se libera un hueco. Sin límite las deja correr todas a la vez. El botón «Ver Máximo» estima cuántas puede aguantar este equipo según su RAM y CPU disponibles." />
        </label>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <select className="form-input form-select" style={{ flex: 1 }} value={uploadMaxConcurrent} onChange={e => setUploadMaxConcurrent(Number(e.target.value))}>
            <option value={0}>Sin límite</option>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
          <button
            className="btn btn-secondary btn-sm"
            type="button"
            onClick={handleTestConcurrency}
            disabled={testingConcurrency}
          >
            {testingConcurrency ? 'Consultando…' : 'Ver Máximo'}
          </button>
        </div>
        {concurrencyEstimate && (
          <Modal titulo="Máximo de subidas en paralelo" onClose={() => setConcurrencyEstimate(null)} style={{ maxWidth: 860 }}>
            <div className="modal-body">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Recurso</th>
                    <th>Disponible</th>
                    <th>Uso estimado por 1 subida</th>
                    <th>Qué lo consume</th>
                    <th>Subidas soportadas</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>RAM</td>
                    <td>{concurrencyEstimate.available_ram_gb} GB</td>
                    <td>{concurrencyEstimate.assumed_ram_gb_per_slot} GB</td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      Capturas con FFmpeg: extraer y escalar fotogramas. Es casi todo el gasto.
                    </td>
                    <td>{concurrencyEstimate.ram_limited_to}</td>
                  </tr>
                  <tr>
                    <td>CPU</td>
                    <td>{concurrencyEstimate.cpu_cores} núcleos</td>
                    <td>1 núcleo</td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      Hasheo del torrent con torf: satura un núcleo entero. Y las capturas con FFmpeg.
                    </td>
                    <td>{concurrencyEstimate.cpu_limited_to}</td>
                  </tr>
                </tbody>
              </table>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginTop: 14 }}>
                <span className="form-hint">
                  Estimación orientativa, no tiene en cuenta la velocidad del disco o de la red.
                  El trabajo sobre las pistas no entra en estos números, ni activando «Reordenar
                  pistas»: reordenar con mkvmerge copia los flujos sin recodificar, así que tarda
                  lo que tarde el disco pero apenas gasta RAM ni CPU. Y solo renombrar es aún más
                  barato: mkvpropedit toca la cabecera en el sitio, sin releer el archivo.
                </span>
                <button
                  className="btn btn-secondary btn-sm"
                  type="button"
                  style={{ flexShrink: 0 }}
                  onClick={() => { setUploadMaxConcurrent(concurrencyEstimate.recommended); setConcurrencyEstimate(null) }}
                >
                  Establecer {concurrencyEstimate.recommended}
                </button>
              </div>
            </div>
          </Modal>
        )}
      </div>
      <div className="form-group">
        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          Ignorar Temporadas especiales
          <InfoIcon text="Excluye la temporada especial (temporada 0) del estado global de una serie. Si tienes todas las temporadas y capítulos salvo los especiales, la serie aparece como completa en las columnas Estado y eMuwarez de la Biblioteca. Sus atributos consolidados (resolución, source, códecs, audio y subtítulos) se calculan ignorando los especiales, y en el Panel sus capítulos faltantes no cuentan como faltantes." />
        </label>
        <select className="form-input form-select" value={ignoreSpecials ? 'true' : 'false'} onChange={e => setIgnoreSpecials(e.target.value === 'true')}>
          <option value="true">Sí</option>
          <option value="false">No</option>
        </select>
      </div>
      <div className="form-group">
        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          Máximo de Elementos en Recomendaciones
          <InfoIcon text="Cuántos elementos como máximo se muestran en Recomendaciones. Sin límite los muestra todos." />
        </label>
        <select className="form-input form-select" value={recentLimit} onChange={e => setRecentLimit(Number(e.target.value))}>
          <option value={0}>Sin límite</option>
          {[50, 100, 150, 200, 250, 300].map(n => <option key={n} value={n}>{n}</option>)}
        </select>
      </div>

    </div>
  )
}
